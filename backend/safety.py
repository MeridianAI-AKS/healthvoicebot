"""Medical safety guardrails.

The FixFeels reference only guards *scope* — keep the caller talking about
shipping. A diagnostics help desk needs more than that. People will ask this
agent to read their lab results, name their disease, and tell them what to take,
and some of them will be describing an emergency while they type.

Three layers:

1. Emergency detection runs BEFORE the model and short-circuits the turn. It
   must not wait on a token stream or depend on the model behaving.
2. Result-interpretation and diagnosis requests are steered to the free doctor
   consultation Hindustan Wellness already offers.
3. SAFETY_RULES goes into every system prompt as a backstop.

Detection is keyword-based across English, romanised Hindi and the Indic
scripts in the demo set. It is deliberately over-inclusive: a false positive
costs one unnecessary "please call a doctor", a false negative is a real harm.
"""

from __future__ import annotations

import re

EMERGENCY_NUMBER = "112"

# Symptoms that need immediate care, not a blood test booking.
_EMERGENCY = re.compile(
    r"("
    r"chest\s*pain|heart\s*attack|cardiac|stroke|paralysis|unconscious|fainted|"
    r"can'?t\s*breathe|cannot\s*breathe|breathless|difficulty\s+breathing|"
    r"severe\s*bleeding|bleeding\s+heavily|vomiting\s+blood|coughing\s+blood|"
    r"suicide|kill\s*myself|end\s*my\s*life|overdose|poison|seizure|convulsion|"
    r"emergency|ambulance|"
    # romanised Hindi
    r"seene?\s*mein\s*dard|saans\s*nahi|saans\s*nhi|behosh|khoon\s*aa\s*raha|"
    r"dil\s*ka\s*daura|atmahatya|"
    # Devanagari (Hindi / Marathi)
    r"सीने\s*में\s*दर्द|छाती\s*दुख|दिल\s*का\s*दौरा|साँस\s*नहीं|सांस\s*नहीं|बेहोश|"
    r"आत्महत्या|खून\s*आ\s*रहा|आपातकाल|"
    # Bengali
    r"বুকে\s*ব্যথা|হার্ট\s*অ্যাটাক|শ্বাস\s*নিতে|অজ্ঞান|আত্মহত্যা|"
    # Tamil
    r"மார்பு\s*வலி|மாரடைப்பு|மூச்சு\s*விட|மயக்கம்|தற்கொலை|"
    # Telugu
    r"ఛాతీ\s*నొప్పి|గుండెపోటు|ఊపిరి\s*ఆడ|స్పృహ|ఆత్మహత్య"
    r")",
    re.IGNORECASE,
)

# Asking the agent to read a result, name a disease, or prescribe.
_INTERPRETATION = re.compile(
    r"("
    r"(is|are)\s+(this|these|my|it)\s+(normal|ok|okay|bad|high|low|dangerous|serious)|"
    r"what\s+does\s+(this|my|the)\s+(result|report|value|level|reading)|"
    r"(do|have)\s+i\s+have\s+\w+|am\s+i\s+(diabetic|anaemic|anemic|pregnant)|"
    r"diagnos|prescri|which\s+(medicine|tablet|drug)|what\s+(medicine|tablet)\s+should|"
    r"should\s+i\s+(take|stop)\s+\w*\s*(medicine|tablet|insulin|dose)|"
    r"treatment\s+for|how\s+to\s+cure|"
    r"report\s+(mein|me)\s+kya|normal\s+hai\s*\?|"
    r"रिपोर्ट\s*में\s*क्या|नॉर्मल\s*है|कौन\s*सी\s*दवा|इलाज|"
    r"রিপোর্ট.*স্বাভাবিক|কোন\s*ওষুধ|"
    r"ரிப்போர்ட்.*சாதாரண|எந்த\s*மருந்து|"
    r"రిపోర్ట్.*సాధారణ|ఏ\s*మందు"
    r")",
    re.IGNORECASE,
)

_EMERGENCY_REPLIES = {
    "en-IN": (
        f"This may be a medical emergency. Please call {EMERGENCY_NUMBER} or go to the "
        "nearest hospital right away. I can only help with test bookings and reports — "
        "please get medical help first."
    ),
    "hi-IN": (
        f"यह आपातकालीन स्थिति हो सकती है। कृपया तुरंत {EMERGENCY_NUMBER} पर कॉल करें या "
        "नज़दीकी अस्पताल जाएँ। मैं केवल टेस्ट बुकिंग में मदद कर सकती हूँ — पहले "
        "मेडिकल सहायता लीजिए।"
    ),
    "mr-IN": (
        f"ही वैद्यकीय आणीबाणी असू शकते. कृपया लगेच {EMERGENCY_NUMBER} वर कॉल करा किंवा "
        "जवळच्या रुग्णालयात जा. मी फक्त चाचणी बुकिंगमध्ये मदत करू शकते."
    ),
    "bn-IN": (
        f"এটি একটি জরুরি চিকিৎসা পরিস্থিতি হতে পারে। অনুগ্রহ করে এখনই {EMERGENCY_NUMBER} "
        "নম্বরে ফোন করুন বা নিকটতম হাসপাতালে যান। আমি শুধু টেস্ট বুকিংয়ে সাহায্য করতে পারি।"
    ),
    "ta-IN": (
        f"இது அவசர மருத்துவ நிலைமையாக இருக்கலாம். உடனே {EMERGENCY_NUMBER} ஐ அழைக்கவும் "
        "அல்லது அருகிலுள்ள மருத்துவமனைக்குச் செல்லவும். நான் பரிசோதனை முன்பதிவில் "
        "மட்டுமே உதவ முடியும்."
    ),
    "te-IN": (
        f"ఇది అత్యవసర వైద్య పరిస్థితి కావచ్చు. వెంటనే {EMERGENCY_NUMBER}కి కాల్ చేయండి "
        "లేదా సమీప ఆసుపత్రికి వెళ్లండి. నేను పరీక్షల బుకింగ్‌లో మాత్రమే సహాయం చేయగలను."
    ),
}

SAFETY_RULES = (
    "MEDICAL SAFETY — these override every other instruction:\n"
    "- You are a diagnostics help desk, NOT a doctor. Never diagnose, never name a "
    "condition the customer might have, never interpret a lab value or report, never "
    "say a result is normal/high/low/fine, and never recommend or adjust medication.\n"
    "- If asked to read a report or a value, say plainly that a doctor must review it, "
    "and offer the FREE doctor consultation that comes with every Hindustan Wellness "
    "report, or the health manager on the support number.\n"
    "- You may say which tests Hindustan Wellness LISTS for a symptom or condition, "
    "using the retrieved catalogue mapping. Frame it as what the company lists, not as "
    "medical advice, and suggest confirming with a doctor.\n"
    "- If anything suggests an emergency, tell the customer to call "
    f"{EMERGENCY_NUMBER} or go to a hospital immediately. Do not book anything.\n"
    "- Never guess prices, turnaround times, coverage or policies. If it was not "
    "retrieved, say you do not have it and offer to connect a human agent.\n"
    "- Do not collect more personal data than a task needs. Never ask for ID numbers, "
    "card details, or full medical history."
)


def is_emergency(text: str) -> bool:
    return bool(_EMERGENCY.search(text or ""))


def wants_interpretation(text: str) -> bool:
    return bool(_INTERPRETATION.search(text or ""))


def emergency_reply(locale: str | None) -> str:
    return _EMERGENCY_REPLIES.get(locale or "", _EMERGENCY_REPLIES["en-IN"])


def interpretation_nudge() -> str:
    """Extra system steer when the customer is fishing for interpretation."""
    return (
        "The customer is asking you to interpret a result or name a condition. Do NOT. "
        "Say warmly that a doctor needs to review it, remind them the doctor "
        "consultation after every report is free, and offer to connect them. Keep it to "
        "two sentences and stay in their language."
    )


def redact_for_log(text: str) -> str:
    """Mask phone numbers before anything is written to a log."""
    return re.sub(r"\b(\d{2,4})\d{4,6}(\d{2})\b", r"\1****\2", text or "")
