from google import genai
from google.genai import types
import os
import re
import json
from dotenv import load_dotenv
from schemas import QuestionResponse

load_dotenv()

# ---------------------------------------------------------
# 1. CLIENT SETUP
# ---------------------------------------------------------
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# ---------------------------------------------------------
# 2. QUALITY GATES (The Referee)
# ---------------------------------------------------------
def validate_quality_gates(response: QuestionResponse):
    errors = []
    
    # --- HELPER FUNCTIONS ---
    def check_readability(text, frame_name):
        # Rule: < 15 seconds to read
        word_count = len(text.split())
        if word_count > 50:
            return f"{frame_name} is too long ({word_count} words). Keep it under 15 seconds."
        # Rule: Natural speech rhythm
        if re.search(r"\b(do not|cannot|will not|is not)\b", text, re.IGNORECASE):
            return f"{frame_name} sounds robotic. Use contractions (don't, can't)."
        return None

    def check_specificity(text, frame_name):
        # Rule: Must force elaboration. No Yes/No questions.
        if re.match(r"^(Do|Are|Is|Can|Will|Did)\s", text, re.IGNORECASE) and not re.search(r"\b(why|how|what|tell me)\b", text, re.IGNORECASE):
            return f"{frame_name} is a Yes/No question. Must force elaboration."
        return None

    def check_tone_safety_and_framing(text, frame_name):
        # Rule: No "Boy"
        if re.search(r"\bboy\b", text, re.IGNORECASE):
            return f"{frame_name} uses 'boy'. Use 'partner', 'friend', or 'he'."
        # Rule: Signal-First (No Interview Mode)
        if re.search(r"\b(rate|scale|demonstrate|highlight)\b", text, re.IGNORECASE):
            return f"{frame_name} sounds like an interview. Use casual language."
        # Rule: Safety
        if re.search(r"\b(toxic|stupid|hate|caste|politics|religion)\b", text, re.IGNORECASE):
            return f"{frame_name} contains unsafe/sensitive terms."
        # Rule: No Romantic Framing
        if re.search(r"\b(dating|ex-girlfriend|past relationship|breakup|dating app|date)\b", text, re.IGNORECASE):
            return f"{frame_name} violates 'No Romantic Framing'. Focus on general life/career/family values."
        return None

    # --- FRAME CHECKS (Section 1.3) ---

    # [cite_start]1. ADVISOR FRAME [cite: 63-66]
    if re.search(r"what would you do", response.advisor_question, re.IGNORECASE):
        errors.append("Advisor Error: Found 'What would you do'. Must ask 'What advice would you give HIM?'.")
    if "you" in response.advisor_question.lower()[:20]: 
         errors.append("Advisor Error: Scenario starts with 'You'. Must start with 'A friend/colleague/cousin'.")
    
    msg = check_readability(response.advisor_question, "Advisor Q")
    if msg: errors.append(msg)
    msg = check_tone_safety_and_framing(response.advisor_question, "Advisor Q")
    if msg: errors.append(msg)

    # [cite_start]2. HYPE/FLEX FRAME [cite: 67-70]
    # Constraint: No negative tone words
    if re.search(r"\b(fail|regret|mistake|worst|bad|hate|wrong)\b", response.hype_question, re.IGNORECASE):
        errors.append("Hype Error: Found negative tone word. Must focus on 'positive or aspiring' traits.")
    
    # FIXED: Expanded regex to match valid Doc examples like "What is one...", "What deliberate step..."
    valid_hype_triggers = r"\b(time|instance|moment|situation|one|specific|step|system|habit|skill|thing)\b"
    if not re.search(valid_hype_triggers, response.hype_question, re.IGNORECASE):
        errors.append("Hype Error: Must ask for a 'specific instance' (e.g., 'Tell me about a time', 'What is one thing').")
        
    # Constraint: Past Tense
    if re.search(r"\b(will|plan|going to|future)\b", response.hype_question, re.IGNORECASE):
        errors.append("Hype Error: Found future tense. Must ask for PAST evidence.")

    msg = check_readability(response.hype_question, "Hype Q")
    if msg: errors.append(msg)
    msg = check_tone_safety_and_framing(response.hype_question, "Hype Q")
    if msg: errors.append(msg)

    # [cite_start]3. HOT TAKE FRAME [cite: 71-74]
    social_anchors = ["people", "say", "social media", "twitter", "trend", "instagram", "society", "many professionals", "often said"]
    if not any(anchor in response.hot_take_question.lower() for anchor in social_anchors):
        errors.append("Hot Take Error: Missing social anchor (e.g., 'Many professionals say...', 'Social media says...').")
    
    msg = check_specificity(response.hot_take_question, "Hot Take Q")
    if msg: errors.append(msg)

    return errors

# ---------------------------------------------------------
# 3. PROMPT & GENERATION
# ---------------------------------------------------------
def build_system_prompt(req, error_feedback=""):
    # [cite_start]DEFINITIONS [cite: 11, 59-61]
    intensity_definition = ""
    if req.intensity == "Non-Negotiable":
        intensity_definition = "Priority: Dealbreaker if absent. Tone: Direct checks (but still conversational)."
    elif req.intensity == "Important":
        intensity_definition = "Priority: Very important to partner selection. Tone: Standard behavioral probes."
    elif req.intensity == "Nice to Have":
        intensity_definition = "Priority: Would be nice, but not essential. Tone: Lighter, more playful phrasing."

    base_prompt = f"""
    You are an expert Relationship Psychologist for 'Nazar'.
    
    CONTEXT:
    User: {req.girl_persona}
    Target: {req.boy_persona}
    
    TASK: Generate 3 screening questions.
    Domain: {req.domain}
    Subdomain: {req.subdomain}
    
    # INPUTS
    Subdomain Description/Alignment: {req.aspiration} 
    Intensity: {req.intensity} ({intensity_definition})
    
    ### FRAME RULES (STRICTLY ADHERE TO SECTION 1.3):
    1. [cite_start]ADVISOR FRAME (Third-Person Rule) [cite: 63-66]
       - GOAL: Ask user to advice on a hypothetical Indian family/social situation (friend/relative).
       - CONSTRAINT: NEVER ask "What would you do?".
       - CONTEXT: Indian family/social context (e.g., relatives visiting, parents).

    2. [cite_start]HYPE/FLEX FRAME (Evidence Rule) [cite: 67-70]
       - GOAL: Ask user to share views on something POSITIVE or ASPIRING about himself.
       - CONSTRAINT: No negative tone. Must ask for a SPECIFIC INSTANCE (not general habit).
       - CONTEXT: Investment, life choice, redefining standards, milestones.

    3. [cite_start]HOT TAKE FRAME (Social Rule) [cite: 71-74]
       - GOAL: Reveal stance on a popular social hot topic in Indian context.
       - CONSTRAINT: Anchor to a social observation first.
       - TEMPLATE: "Many professionals say [Observation]. Does this feel true for you?"

    ### [cite_start]GENERAL CONSTRAINTS [cite: 88-99]:
    - No "Boy" (Use "partner"/"he").
    - No Romantic/Dating framing (Focus on Life/Work/Family).
    - Natural Speech (Use contractions).

    ### FEW-SHOT TRAINING (FULL DATA BANK FROM DOC v0.1):
    
    [ADVISOR FRAME - GOOD EXAMPLES]
    - "A married man still asks his mom to weigh in on every emotional argument with his wife. What’s the first boundary he needs to set to protect his marriage?"
    - "If a couple is saving for their future but family members expect them to fund a large, unplanned event, how should the husband handle that conversation without causing a rift?"
    - "If a couple is 100% aligned on a big move or career change but the family strongly disagrees, whose voice should carry more weight in that specific moment?"
    - "A professional repeatedly blames circumstances or people when things don’t go as planned. What would you advise him to change first?"
    - "A man’s progress is consistently blocked because he avoids owning mistakes. What must he urgently change to move forward?"
    - "A professional still seeks his mother’s reassurance for most stressful situations. What would you advise him to change?"
    - "A man cannot act without parental reassurance. What must he urgently work on to become independent?"
    - "A person earns well but struggles to save consistently. What strategy would you advise him to adopt?"
    - "A man has no financial plan despite a steady income. Where should he start immediately to fix this?"
    - "A professional feels stuck but avoids learning new skills. What would you advise him to do?"
    - "A man refuses to upskill despite stagnation. What must he change urgently to survive in his career?"
    - "A person reacts emotionally under stress. What technique would you advise him to practise?"
    - "A man’s emotional reactions regularly harm his results. What is the most critical thing he needs to work on?"

    [ADVISOR FRAME - BAD EXAMPLES]
    - "Imagine a guy who involves his mother in most emotional decisions... What would you advise?" (Too vague/wordy)
    - "What would you do if your mom called too much?" (Violates Third Person Rule)

    [HYPE/FLEX FRAME - GOOD EXAMPLES]
    - "What’s one major life choice—like your career or a personal habit—where you now make the final call without seeking their validation?"
    - "What’s one significant thing you’ve bought or invested in recently that you felt proud to handle entirely on your own without needing to justify it to your family?"
    - "Tell me about a time you took a path that your family wasn't initially sure about—how did you handle that conversation while still keeping the relationship healthy?"
    - "What is one specific situation where you took full responsibility even though it was uncomfortable?"
    - "What is a specific failure you fully owned and corrected through your own effort?"
    - "Tell me about a time you handled a heavy emotional responsibility independently without leaning on your parents."
    - "What emotional responsibility do you think every adult should handle alone, and how do you do that today?"
    - "What financial discipline or system has helped you gain the most control over your money?"
    - "What specific system do you follow to ensure long-term financial stability?"
    - "What is one specific skill you’ve actively worked on to grow professionally?"
    - "What deliberate step have you taken recently to strictly improve your career prospects?"
    - "Walk me through what helps you stay composed during stressful situations?"
    - "What specific habit helps you regulate your emotions when things go wrong?"

    [HYPE/FLEX FRAME - BAD EXAMPLES]
    - "How will you manage finances?" (Violates Past Tense / Specificity)
    - "Do you save money?" (Yes/No Question)
    - "Do you regret your past choices?" (Negative Tone)

    [HOT TAKE FRAME - GOOD EXAMPLES]
    - "People on social media say being a 'Mama’s Boy' is a relationship dealbreaker. Do you think that’s an unfair stereotype, or is it a genuine red flag in modern Indian marriages?"
    - "Many say that financial dependence on family is what’s actually causing the 'delay' in marriage for our generation. Do you agree, or is that just an excuse?"
    - "The old saying is 'You marry the family in India.' Do you think that tradition still holds up today, or should the couple’s autonomy finally take the front seat?"
    - "It’s often said online that people avoid accountability by blaming systems or luck. How do you personally distinguish between legitimate bad luck and your own bad planning?"
    - "If you noticed a lack of accountability was holding you back in life, what specific behavioral changes would you make to break that cycle?"
    - "Social media often discusses emotional dependence on parents. Where do you draw the line between respecting your parents and being emotionally dependent on them?"
    - "If you realized emotional dependence on parents was limiting your personal growth, what is the first boundary you would set to change it?"
    - "Many young professionals say lifestyle inflation eats up savings. What is your personal strategy for keeping that in check?"
    - "What do you think is the biggest mental block that prevents men from fixing bad money habits, and how would you overcome it?"
    - "People often say comfort zones slow career growth. How do you personally recognize when you’ve stayed in a comfort zone too long?"
    - "How do you push yourself to keep growing when the fear of effort or failure kicks in?"
    - "Many professionals say stress affects their behaviour more than they realise. In your experience, what are the subtle signs that stress is taking over someone's actions?"
    - "If you realized emotional control was harming your life outcomes, what mechanism would you put in place to ensure you don't repeat those reactions?"

    [HOT TAKE FRAME - BAD EXAMPLES]
    - "Do you like kids?" (Violates Social Anchor / Yes-No Rule)
    - "On social media, 'mama’s boy' is often used as a red flag. Do you think it’s unfair?" (Too binary, needs elaboration)
    
    ### OUTPUT JSON KEYS:
    advisor_question, hype_question, hot_take_question
    """
    
    if error_feedback:
        base_prompt += f"\n\n!!! PREVIOUS ATTEMPT FAILED !!!\nFIX ERRORS:\n{error_feedback}"
    return base_prompt

async def generate_questions_logic(request_data):
    # GEMINI 3 FLASH PREVIEW
    model_id = 'gemini-3-flash-preview'
    
    max_retries = 3
    current_try = 0
    last_error = "Unknown Error"
    
    while current_try < max_retries:
        print(f"Attempt {current_try + 1} using {model_id}...")
        prompt = build_system_prompt(request_data, last_error)
        
        try:
            # Generate Content using New SDK
            response = client.models.generate_content(
                model=model_id,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )
            
            # Clean and Parse JSON
            clean_text = response.text.replace("```json", "").replace("```", "").strip()
            parsed_response = QuestionResponse.model_validate_json(clean_text)
            
            # Validate Quality Gates
            validation_errors = validate_quality_gates(parsed_response)
            
            if not validation_errors:
                return parsed_response
            
            # If validation fails, retry with feedback
            last_error = "; ".join(validation_errors)
            print(f"Validation Failed: {last_error}")
            current_try += 1
            
        except Exception as e:
            error_str = str(e)
            # Handle potential 404 if model not available in region
            if "404" in error_str:
                last_error = f"Model {model_id} not found. Check permissions/region."
            else:
                last_error = f"System Exception: {error_str}"
            print(f"Error: {last_error}")
            current_try += 1
            
    raise Exception(f"Failed after {max_retries} attempts. \nLast Errors: {last_error}")