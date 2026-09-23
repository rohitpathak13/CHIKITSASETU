"""
CHIKITSASETU AI Health Assistant - Built-in Clinical Knowledge Provider
Robust, deterministic, and fully offline-capable clinical reasoning and RAG engine.
Operates with zero external network calls or cloud API keys.
"""
import re
from typing import Optional, Dict, Any, List
from backend.chatbot.providers.base import AIProviderBase
from backend.chatbot.schemas import UploadedFileMeta, LanguageEnum
from backend.chatbot.retrieval.knowledge_base import (
    MEDICINE_KNOWLEDGE_BASE,
    LAB_TEST_REFERENCE_RANGES,
    RADIOLOGY_GLOSSARY
)
from backend.chatbot.retrieval.retriever import (
    find_medicine_knowledge,
    find_lab_param_knowledge,
    find_radiology_term_explanation,
    triage_symptoms_to_department
)


class LocalBuiltinProvider(AIProviderBase):
    """Offline clinical reasoning engine providing structured, safe educational health assistance."""

    name: str = "local"

    def generate_response(
        self,
        prompt: str,
        system_prompt: str,
        language: LanguageEnum = LanguageEnum.ENGLISH,
        file_meta: Optional[UploadedFileMeta] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        prompt_lower = prompt.lower()
        extracted_text = file_meta.extracted_text if file_meta else ""
        combined_text = f"{prompt} {extracted_text}".lower()

        # 1. Check if user is asking about patient's own active prescriptions
        if context and context.get("authorized") and any(k in prompt_lower for k in ["my medicine", "my prescription", "meri dawai", "meri dawa"]):
            rx_list = context.get("prescriptions", [])
            if rx_list:
                return self._format_patient_prescriptions(rx_list, language)

        # 2. Check if user is asking about patient's own recent lab tests
        if context and context.get("authorized") and any(k in prompt_lower for k in ["my lab", "my report", "meri report", "test result"]):
            labs = context.get("recent_labs", [])
            if labs:
                return self._format_patient_labs(labs, language)

        # 3. Check for specific medicine queries
        med_info = find_medicine_knowledge(combined_text)
        if med_info or any(k in prompt_lower for k in ["medicine", "dawai", "tablet", "capsule", "dawa", "kya kaam karti"]):
            return self._format_medicine_response(med_info, prompt, language)

        # 4. Check for X-Ray report queries
        if any(k in combined_text for k in ["x-ray", "xray", "radiology", "cxr", "degenerative", "consolidation", "opacity"]):
            return self._format_xray_response(combined_text, language)

        # 5. Check for Laboratory report queries
        if any(k in combined_text for k in ["hemoglobin", "wbc", "platelet", "glucose", "sugar", "creatinine", "tsh", "cholesterol", "cbc", "lft", "kft"]):
            return self._format_lab_report_response(combined_text, language)

        # 6. Check for Visible Health Image upload (skin rash, redness, swelling)
        if file_meta and file_meta.file_type == "image":
            return self._format_image_observation_response(prompt, language)

        # 7. Check for Symptoms / General Health Concern
        triage = triage_symptoms_to_department(prompt)
        return self._format_symptom_response(prompt, triage, language)

    # --------------------------------------------------------------------------
    # Sub-generators
    # --------------------------------------------------------------------------

    def _format_medicine_response(self, med: Optional[Dict[str, Any]], query: str, lang: LanguageEnum) -> str:
        if med:
            if lang == LanguageEnum.HINDI:
                return (
                    f"### ℹ️ दवा की जानकारी ({med['generic']})\n"
                    f"**श्रेणी (Category):** {med['category']}\n\n"
                    f"**मुख्य उपयोग (Common Uses):**\n{med['common_uses']}\n\n"
                    f"**यह कैसे काम करती है (How it works):**\n{med['how_it_works']}\n\n"
                    f"### ⚠️ सावधानियां एवं निर्देश (Precautions)\n"
                    f"- {med['precautions']}\n"
                    f"- **संभावित सामान्य दुष्प्रभाव (Side Effects):** {med['side_effects']}\n"
                    f"- **महत्वपूर्ण चेतावनी:** {med['warnings']}\n\n"
                    f"### 👨‍⚕️ डॉक्टर की सलाह\n"
                    f"दवा की सटीक खुराक (Dosage) और समय केवल आपके डॉक्टर या फार्मासिस्ट द्वारा निर्धारित किया जाना चाहिए। "
                    f"दवा को स्वयं से शुरू या बंद न करें।\n\n"
                    f"### ⚠️ महत्वपूर्ण सूचना\n"
                    f"यह जानकारी केवल शैक्षिक उद्देश्यों के लिए है और डॉक्टर के परामर्श का विकल्प नहीं है।"
                )
            elif lang == LanguageEnum.HINGLISH:
                return (
                    f"### ℹ️ Medicine Information ({med['generic']})\n"
                    f"**Category:** {med['category']}\n\n"
                    f"**Kiske liye use hoti hai (Purpose):**\n{med['common_uses']}\n\n"
                    f"**Kaise kaam karti hai (Mechanism):**\n{med['how_it_works']}\n\n"
                    f"### ⚠️ Zaroori Baatein & Precautions\n"
                    f"- **Kaise lein:** {med['precautions']}\n"
                    f"- **Common side effects:** {med['side_effects']}\n"
                    f"- **Warning:** {med['warnings']}\n\n"
                    f"### 👨‍⚕️ Doctor ki Salah\n"
                    f"Apne doctor ya pharmacist dwara prescribe ki gayi exact dosage aur timing ka palan karein. "
                    f"Bina doctor ke mashware ke dawa ka dose na badlein aur na hi band karein.\n\n"
                    f"### ⚠️ Important Notice\n"
                    f"Yeh information sirf educational purpose ke liye hai. Medical advice ke liye doctor se sampark karein."
                )
            else:
                return (
                    f"### ℹ️ Medicine Overview: {med['generic']}\n"
                    f"**Pharmacological Class:** {med['category']}\n\n"
                    f"**Primary Therapeutic Uses:**\n{med['common_uses']}\n\n"
                    f"**Mechanism of Action:**\n{med['how_it_works']}\n\n"
                    f"### 🔍 Key Precautions & Administration\n"
                    f"- {med['precautions']}\n"
                    f"- **Commonly Reported Side Effects:** {med['side_effects']}\n"
                    f"- **Clinical Warnings:** {med['warnings']}\n\n"
                    f"### 👨‍⚕️ Professional Guidance\n"
                    f"Always adhere strictly to the dosage, frequency, and duration specified on your doctor's prescription. "
                    f"Do not adjust your regimen independently. Consult your pharmacist if you experience unexpected reactions.\n\n"
                    f"### ⚠️ Important Notice\n"
                    f"This summary is for educational reference only and does not constitute medical prescription or clinical endorsement."
                )
        else:
            if lang == LanguageEnum.HINGLISH:
                return (
                    "### ℹ️ Medicine Search\n"
                    "Aapne jis medicine ke baare me pucha hai, kripya uska sahi naam ya generic formula likhein.\n\n"
                    "### 🔍 Common Medicines\n"
                    "Aap Paracetamol, Metformin, Pantoprazole, Atorvastatin, Amlodipine, Azithromycin, ya Cetirizine jaisi dawaiyon ke baare me puch sakte hain.\n\n"
                    "### 👨‍⚕️ Doctor Consultation\n"
                    "Agar aapko koi naya prescription mila hai, to hamare hospital ke General Medicine department me doctor se salah le sakte hain."
                )
            else:
                return (
                    "### ℹ️ Medicine Search\n"
                    "Please provide the specific generic or brand name of the medication you wish to understand.\n\n"
                    "### 🔍 Available Reference Formulary\n"
                    "You can inquire about common hospital medicines such as Paracetamol, Metformin, Pantoprazole, Atorvastatin, Amlodipine, Azithromycin, Ibuprofen, and Cetirizine.\n\n"
                    "### 👨‍⚕️ Medical Guidance\n"
                    "Never start or discontinue prescription medication without reviewing with your attending physician."
                )

    def _format_xray_response(self, text: str, lang: LanguageEnum) -> str:
        matched_terms: List[str] = []
        for term, explanation in RADIOLOGY_GLOSSARY.items():
            if term in text:
                matched_terms.append(f"- **{term.title()}:** {explanation}")

        terms_summary = "\n".join(matched_terms) if matched_terms else (
            "- **Degenerative Changes:** Mild age-related wear and tear in cartilage or joints.\n"
            "- **Opacity / Infiltrate:** An area of increased tissue density on film requiring clinical correlation.\n"
            "- **Cardiomegaly:** An enlarged radiographic appearance of the heart silhouette."
        )

        if lang == LanguageEnum.HINGLISH:
            return (
                "### ℹ️ X-Ray Report ki Saral Vyakhya (Simple Explanation)\n"
                "Yeh explanation aapke X-ray report me likhi hui technical bhasha ko aasan shabdon me samjhane ke liye hai:\n\n"
                f"{terms_summary}\n\n"
                "### 🔍 Iska Kya Matlab Hai?\n"
                "X-ray report radiological observations describe karti hai. Iska antim nishkarsh patient ke sharirik jaanch (physical examination) aur symptoms ke sath milakar hi nikala jata hai.\n\n"
                "### 👨‍⚕️ Recommended Specialty\n"
                "Haddiyon ya jodon ki takleef ke liye **Orthopedics** ya fefdon ki jaanch ke liye **Pulmonology / General Medicine** specialist se sampark karein.\n\n"
                "### ⚠️ Important Notice\n"
                "AI Assistant radiologist ka kaam nahi karta. Kripya apne treating doctor se report zaroor discuss karein."
            )
        else:
            return (
                "### ℹ️ Understanding Your X-Ray / Radiology Report\n"
                "Below is a translation of common technical radiological terminology into simple concepts:\n\n"
                f"{terms_summary}\n\n"
                "### 🔍 Clinical Interpretation\n"
                "An X-ray report describes structural densities, bone alignment, and visible patterns. A radiological finding "
                "must always be correlated with your physical examination, clinical history, and symptoms by your treating physician.\n\n"
                "### 👨‍⚕️ Recommended Specialty & Next Steps\n"
                "For bone, joint, or spine findings, schedule a review with an **Orthopedic Specialist**. "
                "For chest X-ray findings, consult a **Pulmonologist or General Physician**.\n\n"
                "### ⚠️ Important Notice\n"
                "This is an educational explanation of written findings, not an independent radiological diagnosis."
            )

    def _format_lab_report_response(self, text: str, lang: LanguageEnum) -> str:
        matched_params: List[str] = []
        for key, info in LAB_TEST_REFERENCE_RANGES.items():
            if key in text or info["test_name"].lower() in text:
                matched_params.append(
                    f"**{info['test_name']}** ({info['category']}):\n"
                    f"- *Reference Interval:* `{info['standard_range']}`\n"
                    f"- *What Low May Mean:* {info['low_meaning']}\n"
                    f"- *What High May Mean:* {info['high_meaning']}\n"
                )

        params_text = "\n".join(matched_params[:4]) if matched_params else (
            "**Complete Blood Count & Metabolic Profile:**\n"
            "- *Hemoglobin (Hb):* Normal 12.0 - 17.5 g/dL (Oxygen-carrying capacity).\n"
            "- *Platelets:* Normal 150,000 - 450,000 /uL (Crucial for blood clotting).\n"
            "- *Fasting Glucose:* Normal 70 - 99 mg/dL (Blood sugar regulation).\n"
            "- *Serum Creatinine:* Normal 0.7 - 1.3 mg/dL (Kidney filtration health)."
        )

        if lang == LanguageEnum.HINGLISH:
            return (
                "### ℹ️ Laboratory Report Parameters\n"
                "Aapke lab test parameters ki standard reference range aur unka matlab:\n\n"
                f"{params_text}\n\n"
                "### 🔍 Mahatvapurna Baatein\n"
                "1. Alag-alag laboratories ke reference ranges me thoda farak ho sakta hai.\n"
                "2. Kisi ek test value ka thoda upar ya neeche hona hamesha bimari ka saboot nahi hota; dehydration ya diet se bhi fark padta hai.\n\n"
                "### 👨‍⚕️ Agla Kadam (Next Steps)\n"
                "Reports ko apne doctor ko dikhayein taaki sahi clinical context me unka nishkarsh nikala ja sake.\n\n"
                "### ⚠️ Important Notice\n"
                "Laboratory values require professional clinical correlation."
            )
        else:
            return (
                "### ℹ️ Laboratory Report Interpretation\n"
                "Here is an educational overview of the referenced laboratory parameters:\n\n"
                f"{params_text}\n\n"
                "### 🔍 Key Context on Reference Ranges\n"
                "- Standard reference intervals may vary slightly between diagnostic laboratories based on assay equipment and calibrators.\n"
                "- Isolated out-of-range figures do not constitute a definitive medical diagnosis on their own; factors such as hydration, recent meals, physical exertion, and medications can cause temporary fluctuations.\n\n"
                "### 👨‍⚕️ Recommended Medical Follow-Up\n"
                "Share these numerical results with your ordering physician to review them against your overall clinical presentation.\n\n"
                "### ⚠️ Important Notice\n"
                "This breakdown is for educational clarity and cannot replace professional medical interpretation."
            )

    def _format_image_observation_response(self, prompt: str, lang: LanguageEnum) -> str:
        if lang == LanguageEnum.HINGLISH:
            return (
                "### ℹ️ Image Observations (Visual Features)\n"
                "Aapki upload ki gayi image ke aadhar par visible features (jaise redness, rash, ya swelling) notice kiye ja sakte hain.\n\n"
                "### 🔍 Sambhavit Kaaran (Possible Categories)\n"
                "Skin par hone wale badlav kai alag-alag kaaranon se ho sakte hain, jaise:\n"
                "- Contact irritation ya kisi product se allergy\n"
                "- Superficial skin dermatitis ya fungal/bacterial infection\n"
                "- Seasonal dryness ya heat rash\n\n"
                "Kyunki kai alag-alag conditions dekhne me bilkul ek jaisi lagti hain, isliye keval photo dekhkar koi bimari tay nahi ki ja sakti.\n\n"
                "### 👨‍⚕️ Recommended Specialty\n"
                "Sahi jaanch aur treatment ke liye **Dermatology (Skin Specialist)** se physical checkup karwayein.\n\n"
                "### 🚨 Kab Turant Doctor ke paas jayein:\n"
                "Agar redness tezi se fail rahi ho, tez bukhar ho, ya achanak tez dard ya pus ban raha ho, to turant hospital jayein.\n\n"
                "### ⚠️ Important Notice\n"
                "AI image inspection diagnostic nahi hai. Kripya bina doctor ke steroid cream ya dawa na lagayein."
            )
        else:
            return (
                "### ℹ️ Visible Condition Observations\n"
                "From the uploaded image, visible surface characteristics such as localized redness, irritation, or swelling can be observed.\n\n"
                "### 🔍 Clinical Interpretation & Categories\n"
                "Visual skin findings can represent a wide spectrum of potential conditions with overlapping physical appearances:\n"
                "- Contact dermatitis or localized allergic reaction\n"
                "- Superficial bacterial or fungal dermatological irritation\n"
                "- Environmental, heat, or friction-induced erythema\n\n"
                "Because numerous benign and inflammatory conditions look identical in photographs, an image alone **cannot** establish a clinical diagnosis.\n\n"
                "### 👨‍⚕️ Recommended Medical Specialty\n"
                "We strongly advise consulting a **Dermatologist or General Physician** for an in-person dermoscopic examination.\n\n"
                "### 🚨 Warning Signs Requiring Urgent Care\n"
                "Seek prompt in-person medical evaluation if the area develops rapid spreading, systemic fever, severe throbbing pain, or purulent discharge.\n\n"
                "### ⚠️ Important Notice\n"
                "This visual analysis is for patient education only. Avoid applying unprescribed topical steroid ointments without medical review."
            )

    def _format_symptom_response(self, text: str, triage: Dict[str, str], lang: LanguageEnum) -> str:
        dept = triage["department"]
        specialty = triage["specialty"]

        if lang == LanguageEnum.HINDI:
            return (
                f"### ℹ️ आपके लक्षणों का अवलोकन\n"
                f"आपने जो लक्षण बताए हैं, उनके आधार पर संभावित चिकित्सीय विभाग: **{specialty}**।\n\n"
                f"### 🔍 संभावित कारण एवं दृष्टिकोण\n"
                f"{triage['rationale']}\n"
                f"कृपया ध्यान दें कि एक जैसे लक्षण कई अलग-अलग सामान्य या मौसमी कारणों से हो सकते हैं। सही कारण जानने के लिए डॉक्टर शारीरिक परीक्षण करते हैं।\n\n"
                f"### 👨‍⚕️ अनुशंसित विशेषज्ञता एवं डॉक्टर\n"
                f"हम आपको चिकित्सा सेतु के **{dept}** विभाग के योग्य डॉक्टर से परामर्श लेने की सलाह देते हैं।\n\n"
                f"### 🚨 तत्काल ध्यान देने योग्य संकेत\n"
                f"यदि आपको अत्यधिक कमजोरी, सांस लेने में तकलीफ, या तेज अनियंत्रित दर्द महसूस हो, तो तुरंत इमरजेंसी विभाग से संपर्क करें।\n\n"
                f"### ⚠️ महत्वपूर्ण सूचना\n"
                f"यह परामर्श केवल शैक्षिक जानकारी प्रदान करता है, कोई अंतिम निदान नहीं।"
            )
        elif lang == LanguageEnum.HINGLISH:
            return (
                f"### ℹ️ Aapke Symptoms ka Overview\n"
                f"Aapke bataye gaye lakshano ke aadhar par sambandhit specialty: **{specialty}**.\n\n"
                f"### 🔍 Sambhavit Kaaran & Understanding\n"
                f"{triage['rationale']}\n"
                f"Dhyan rahe ki ek jaise lakshan kai alag-alag kaaranon (jaise viral infection, stress, ya lifestyle factors) se ho sakte hain. Accurate checkup ke liye doctor clinical history check karte hain.\n\n"
                f"### 👨‍⚕️ Recommended Department & Doctors\n"
                f"Aap hamare hospital ke **{dept}** department me doctor se appointment book kar sakte hain.\n\n"
                f"### 🚨 Kab Emergency Care Lein\n"
                f"Agar bukhar bahut tez ho aur kam na ho raha ho, saans lene me takleef ho, ya severe pain ho, to turant hospital aayein.\n\n"
                f"### ⚠️ Important Notice\n"
                f"Yeh information educational hai aur doctor ke checkup ka vikalp nahi hai."
            )
        else:
            return (
                f"### ℹ️ Symptoms Assessment & Triage\n"
                f"Based on the concerns you described, the most appropriate clinical specialty is **{specialty}**.\n\n"
                f"### 🔍 Potential Categories & Context\n"
                f"{triage['rationale']}\n"
                f"Common symptoms can be shared across diverse clinical conditions ranging from transient infections to systemic factors. A healthcare provider will evaluate your onset timeline, vital signs, and physical indicators to reach an accurate determination.\n\n"
                f"### 👨‍⚕️ Recommended Specialty & Next Steps\n"
                f"We recommend scheduling a clinical consultation with a specialist in the **{dept}** department at CHIKITSASETU.\n\n"
                f"### 🚨 When to Seek Immediate Attention\n"
                f"If you develop red-flag symptoms such as persistent high fever, labored breathing, confusion, or severe intractable pain, please visit the emergency department without delay.\n\n"
                f"### ⚠️ Important Notice\n"
                f"This information is for triage and education only. It does not replace professional medical evaluation."
            )

    def _format_patient_prescriptions(self, rx_list: List[Dict[str, Any]], lang: LanguageEnum) -> str:
        lines: List[str] = []
        for rx in rx_list:
            lines.append(f"**Prescription #{rx['prescription_id']}** (Prescribed by {rx['doctor']} on {rx['date']}):")
            for item in rx["items"]:
                lines.append(f"- **{item['medicine']}** | Dosage: `{item['dosage']}` | Frequency: `{item['frequency']}` | Note: {item['instructions']}")

        body = "\n".join(lines)
        return (
            "### 💊 Your Active Prescriptions (CHIKITSASETU Records)\n"
            f"{body}\n\n"
            "### ⚠️ Important Prescription Rules\n"
            "- Always follow the exact timing and instructions provided by your doctor.\n"
            "- Do not stop or alter your dosage without speaking with your treating physician.\n\n"
            "### ⚠️ Important Notice\n"
            "This summary displays your verified electronic health records for informational reference."
        )

    def _format_patient_labs(self, labs: List[Dict[str, Any]], lang: LanguageEnum) -> str:
        lines: List[str] = []
        for lo in labs:
            lines.append(f"**Lab Order #{lo['order_id']}** (Date: {lo['date']}, Status: `{lo['status']}`):")
            for res in lo["results"]:
                abnormal_flag = "⚠️ Flagged" if res["is_abnormal"] else "Normal"
                lines.append(f"- **{res['parameter']}:** {res['value']} {res['unit']} (Ref: {res['reference']}) [{abnormal_flag}]")

        body = "\n".join(lines)
        return (
            "### 🔬 Your Recent Laboratory Results (CHIKITSASETU Records)\n"
            f"{body}\n\n"
            "### 🔍 Understanding Your Results\n"
            "Parameters marked with a flag should be reviewed with your ordering doctor during your follow-up visit.\n\n"
            "### ⚠️ Important Notice\n"
            "Laboratory results must always be interpreted in conjunction with your clinical symptoms and physical examination."
        )
