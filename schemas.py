from pydantic import BaseModel, Field
from typing import Literal

# ---------------------------------------------------------
# INPUT SCHEMA
# Maps to Document Section: Structure of FQGB [Source: 6-14]
# ---------------------------------------------------------
class QuestionRequest(BaseModel):
    domain: str = Field(
        ..., 
        description="High-level value category (e.g., 'Emotional Maturity') [Source: 7]"
    )
    subdomain: str = Field(
        ..., 
        description="Specific behavioral subset (e.g., 'Mother-Son Dynamics') [Source: 8]"
    )
    aspiration: str = Field(
        ..., 
        description="One line description of what the subdomain stands for [Source: 9]. CRITICAL for context."
    )
    intensity: Literal["NiceToHave", "Important", "Non-Negotiable"] = Field(
        ..., 
        description="Priority level [Source: 11]"
    )
    
    # Persona Context [Source: 12-14]
    girl_persona: str = "Urban Indian woman, 25+, financially independent, professional."
    boy_persona: str = "Urban Indian man, 28+, financially stable."

# ---------------------------------------------------------
# OUTPUT SCHEMA
# Maps to Document Section: Output & Strategy Frames [Source: 15-19]
# ---------------------------------------------------------
class QuestionResponse(BaseModel):
    advisor_question: str = Field(
        ..., 
        description="Third-person scenario. STRICT RULE: No 'What would you do?' [Source: 17, 64]"
    )
    hype_question: str = Field(
        ..., 
        description="Past-tense evidence. STRICT RULE: Must ask 'What DID you do?' [Source: 18, 72]"
    )
    hot_take_question: str = Field(
        ..., 
        description="Social trend reaction. STRICT RULE: Anchor to social observation [Source: 19, 79]"
    )