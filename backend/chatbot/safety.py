"""
CHIKITSASETU AI Health Assistant - Medical Safety & Triage Layer
Detects life-threatening emergencies, flags high-risk symptoms, and enforces non-diagnostic guardrails.
"""
import re
from typing import Tuple, List, Optional
from backend.chatbot.schemas import SafetyEvaluation, SafetyLevel, LanguageEnum


# Red-Flag Emergency Patterns categorized by clinical presentation
EMERGENCY_PATTERNS = {
    "cardiovascular_emergency": [
        r"\b(severe|crushing|heavy|squeezing)\s+(chest\s+pain|chest\s+pressure)\b",
        r"\bchest\s+pain\s+(radiating|going|spreading)\s+to\s+(left\s+arm|jaw|back|neck)\b",
        r"\bheart\s+attack\b",
        r"\bsudden\s+chest\s+pain\s+with\s+(sweating|shortness\s+of\s+breath|dizziness)\b",
        r"\bchhati\s+me(in)?\s+(tez|bahut|tez\s+dard)\b",
        r"\bchhati\s+me(in)?\s+dabav\b",
    ],
    "respiratory_emergency": [
        r"\b(can'?t|cannot|unable\s+to)\s+breathe\b",
        r"\b(gasping\s+for\s+air|suffocating|choking)\b",
        r"\bsevere\s+(shortness\s+of\s+breath|breathing\s+difficulty|breathlessness)\b",
        r"\b(lips|fingers|face)\s+turning\s+(blue|pale)\b",
        r"\bsaans\s+(nahi\s+aa\s+rahi|ruk\s+rahi|lene\s+me\s+bahut\s+takleef)\b",
    ],
    "neurological_stroke": [
        r"\b(face\s+drooping|facial\s+droop)\b",
        r"\b(sudden\s+weakness|paralysis)\s+(in\s+one\s+side|arm|leg)\b",
        r"\b(slurred\s+speech|unable\s+to\s+speak|sudden\s+confusion)\b",
        r"\bsudden\s+loss\s+of\s+(vision|balance)\b",
        r"\bworst\s+headache\s+of\s+(my\s+)?life\b",
        r"\bthunderclap\s+headache\b",
        r"\blakwa|paralysis\b",
    ],
    "severe_allergic_reaction": [
        r"\b(throat\s+closing|swelling\s+in\s+throat|tongue\s+swollen)\b",
        r"\banaphylaxis|anaphylactic\b",
        r"\bdifficulty\s+swallowing\s+with\s+(hives|rash|wheezing)\b",
        r"\bgala\s+band\s+ho\s+raha\b",
    ],
    "severe_hemorrhage": [
        r"\b(uncontrolled|heavy|spurting)\s+bleeding\b",
        r"\bvomiting\s+(blood|coffee\s+ground)\b",
        r"\bcoughing\s+up\s+(blood|large\s+amount\s+of\s+blood)\b",
        r"\bkhoon\s+ki\s+ulti|tez\s+khoon\s+behna\b",
    ],
    "unresponsiveness": [
        r"\b(unconscious|unresponsive|passed\s+out\s+and\s+not\s+waking)\b",
        r"\bseizure\s+(lasting\s+more\s+than|continuous)\b",
        r"\bbehosh|behosh\s+ho\s+gaye\b",
    ],
    "self_harm_emergency": [
        r"\b(suicide|kill\s+myself|end\s+my\s+life|want\s+to\s+die)\b",
        r"\b(overdose|swallowed\s+all\s+my\s+pills)\s+(to\s+die|on\s+purpose)?\b",
        r"\bself\s*harm\b",
        r"\batmahatya|jaan\s+dena\b",
    ]
}

# Dangerous / Prohibited diagnosis and prescribing words for post-checking
DIAGNOSTIC_ASSERTION_PATTERNS = [
    r"\byou\s+(definitely\s+have|are\s+diagnosed\s+with|suffer\s+from)\s+[A-Za-z\s]+\b",
    r"\bdiagnosis\s+is\s+confirmed\s+as\b",
]

PRESCRIPTIVE_COMMAND_PATTERNS = [
    r"\btake\s+\d+(\.\d+)?\s*(mg|ml|tablets?|capsules?)\s+(twice|thrice|daily|every)\b",
    r"\bstop\s+taking\s+your\s+(prescribed|current)\s+medicine\b",
    r"\bincrease\s+your\s+dosage\s+to\b",
]


def evaluate_safety(text: str) -> SafetyEvaluation:
    """
    Performs deterministic pre-execution clinical safety screening.
    Detects acute life-threatening situations and returns a SafetyEvaluation object.
    """
    if not text:
        return SafetyEvaluation(level=SafetyLevel.SAFE)

    text_lower = text.lower()
    matched_triggers: List[str] = []
    emergency_type: Optional[str] = None

    for cat_name, patterns in EMERGENCY_PATTERNS.items():
        for pat in patterns:
            match = re.search(pat, text_lower, re.IGNORECASE)
            if match:
                matched_triggers.append(match.group(0))
                if not emergency_type:
                    emergency_type = cat_name

    if matched_triggers:
        return SafetyEvaluation(
            level=SafetyLevel.EMERGENCY,
            is_emergency=True,
            emergency_type=emergency_type,
            warning_message="POTENTIAL MEDICAL EMERGENCY DETECTED",
            trigger_phrases=matched_triggers
        )

    return SafetyEvaluation(level=SafetyLevel.SAFE)


def build_emergency_response(safety: SafetyEvaluation, language: LanguageEnum = LanguageEnum.ENGLISH) -> str:
    """
    Constructs an immediate, high-priority emergency advisory directing the user to
    emergency medical facilities without delay.
    """
    if language == LanguageEnum.HINDI:
        return (
            "🚨 **आपातकालीन चेतावनी / MEDICAL EMERGENCY ALERT**\n\n"
            "आपके द्वारा बताए गए लक्षण किसी **गंभीर या आपातकालीन स्वास्थ्य स्थिति** का संकेत हो सकते हैं। "
            "कृपया चैटबॉट से सलाह लेने में समय व्यर्थ न करें और तुरंत आपातकालीन सहायता प्राप्त करें।\n\n"
            "### 📞 तत्काल संपर्क करें:\n"
            "- **राष्ट्रीय आपातकालीन एम्बुलेंस सेवा:** 108 / 112\n"
            "- **चिकित्सा सेतु अस्पताल इमरजेंसी डेस्क:** 24x7 कैजुअल्टी वार्ड\n"
            "- यदि आप भारत से बाहर हैं, तो अपने स्थानीय आपातकालीन नंबर (जैसे 911 / 999) पर संपर्क करें।\n\n"
            "### ⚠️ क्या करें:\n"
            "1. तुरंत अपने नजदीकी अस्पताल के इमरजेंसी (Casualty) विभाग में जाएं।\n"
            "2. खुद गाड़ी चलाकर न जाएं; किसी परिजन, एम्बुलेंस या पड़ोसी की मदद लें।\n"
            "3. यदि आप किसी के साथ हैं, तो उन्हें अपनी स्थिति के बारे में बताएं।\n\n"
            "*(यह चैटबॉट आपातकालीन स्थिति को संभालने के लिए नहीं है।)*"
        )
    elif language == LanguageEnum.HINGLISH:
        return (
            "🚨 **MEDICAL EMERGENCY ALERT / AAPATKAALEEN CHETAVANI**\n\n"
            "Aapke bataye hue lakshan ek **serious medical emergency** ke ho sakte hain. "
            "Kripya chatbot par intezar na karein aur turant emergency medical care prapt karein.\n\n"
            "### 📞 Turant Contact Karein:\n"
            "- **National Ambulance / Emergency:** 108 / 112\n"
            "- **CHIKITSASETU Hospital 24x7 Casualty & Emergency Ward**\n"
            "- International users: Apne local emergency number (e.g. 911 / 999) par call karein.\n\n"
            "### ⚠️ Immediate Action:\n"
            "1. Bina deri kiye nazdeeki hospital ke Emergency Room / Casualty jayein.\n"
            "2. Khud drive na karein; ambulance ya family member ki madad lein.\n"
            "3. Agar saans lene me ya chhati me takleef hai, to aaram se baithein aur shaant rahein.\n\n"
            "*(AI Assistant cannot handle emergency situations. Seek in-person hospital care immediately.)*"
        )
    else:
        return (
            "🚨 **CRITICAL MEDICAL EMERGENCY ALERT**\n\n"
            "The symptoms you described may indicate a **life-threatening or acute medical emergency**. "
            "Do not delay seeking in-person clinical attention.\n\n"
            "### 📞 Call Emergency Services Immediately:\n"
            "- **Emergency / Ambulance:** **108** or **112** (India) / **911** (US) / **999** (UK)\n"
            "- **CHIKITSASETU 24x7 Emergency & Trauma Department**\n\n"
            "### ⚠️ Immediate Instructions:\n"
            "1. Proceed to the nearest hospital emergency room (ER/Casualty) immediately.\n"
            "2. **Do not drive yourself.** Call an ambulance or have someone accompany you.\n"
            "3. If experiencing chest pain or severe shortness of breath, sit upright, stay calm, and loosen tight clothing.\n\n"
            "*(This AI Health Assistant is for general education only and cannot treat or manage medical emergencies.)*"
        )


def sanitize_generated_response(text: str) -> str:
    """
    Post-processes LLM-generated output to mitigate any diagnostic assertions or
    prescriptive dosage mandates before rendering to the end-user.
    """
    sanitized = text

    # Remove or qualify definitive diagnosis phrases
    sanitized = re.sub(
        r"\b(you have|you are suffering from)\s+([A-Za-z\s]+?)\b",
        r"your symptoms may be consistent with \2",
        sanitized,
        flags=re.IGNORECASE
    )

    # Ensure mandatory educational disclaimer is present
    if "educational" not in sanitized.lower() and "disclaimer" not in sanitized.lower():
        sanitized += (
            "\n\n---\n*Disclaimer: This information is for educational purposes only and does not replace "
            "evaluation or diagnosis by a qualified healthcare professional. Do not start or alter medication "
            "without consulting your doctor.*"
        )

    return sanitized
