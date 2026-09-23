"""
CHIKITSASETU AI Health Assistant - Medical Knowledge Base
Educational data for medicines, laboratory reference values, radiologic terminology, and specialty triage.
"""
from typing import Dict, Any, List, Optional


# Curated educational database of commonly prescribed medicines and classes
MEDICINE_KNOWLEDGE_BASE: Dict[str, Dict[str, Any]] = {
    "paracetamol": {
        "generic": "Paracetamol (Acetaminophen)",
        "category": "Analgesic & Antipyretic",
        "common_uses": "Relief of mild-to-moderate pain, headaches, muscle aches, and fever reduction.",
        "how_it_works": "Acts on the central nervous system to inhibit prostaglandin synthesis and regulate body temperature via the hypothalamus.",
        "precautions": "Take with water. Do not exceed the maximum daily limit (typically 4000mg in 24 hours for adults). Avoid concurrent use with other medications containing paracetamol.",
        "side_effects": "Generally well tolerated at therapeutic doses. Rare: allergic rash, nausea.",
        "warnings": "Caution in patients with liver impairment or chronic alcohol consumption. Follow doctor's dosage."
    },
    "metformin": {
        "generic": "Metformin Hydrochloride",
        "category": "Biguanide / Antidiabetic",
        "common_uses": "First-line oral management of Type 2 Diabetes Mellitus; improves glycemic control.",
        "how_it_works": "Decreases hepatic glucose production, decreases intestinal absorption of glucose, and improves insulin sensitivity.",
        "precautions": "Take with or immediately after meals to reduce gastrointestinal side effects.",
        "side_effects": "Nausea, diarrhea, abdominal cramps, metallic taste, loss of appetite.",
        "warnings": "Requires kidney function monitoring. Temporary discontinuation required before iodine contrast procedures. Rare risk of lactic acidosis."
    },
    "amoxicillin": {
        "generic": "Amoxicillin",
        "category": "Penicillin-class Antibiotic",
        "common_uses": "Bacterial infections of the respiratory tract, ear/nose/throat, urinary tract, and skin.",
        "how_it_works": "Inhibits bacterial cell wall synthesis during active multiplication.",
        "precautions": "Complete the full course prescribed by your doctor even if you feel better earlier. Do not share antibiotics.",
        "side_effects": "Diarrhea, mild skin rash, stomach upset, nausea.",
        "warnings": "Contraindicated in individuals with penicillin allergy. Ineffective against viral infections (common cold, flu)."
    },
    "pantoprazole": {
        "generic": "Pantoprazole",
        "category": "Proton Pump Inhibitor (PPI)",
        "common_uses": "Gastroesophageal reflux disease (GERD), acid peptic disease, stomach ulcers, and gastric protection during painkiller therapy.",
        "how_it_works": "Suppresses gastric basal and stimulated acid secretion by inhibiting the H+/K+-ATPase enzyme system.",
        "precautions": "Usually taken once daily in the morning, 30 to 60 minutes before breakfast.",
        "side_effects": "Headache, diarrhea, bloating, constipation.",
        "warnings": "Long-term unmonitored use may affect magnesium and vitamin B12 absorption. Follow doctor's recommended duration."
    },
    "atorvastatin": {
        "generic": "Atorvastatin Calcium",
        "category": "HMG-CoA Reductase Inhibitor (Statin)",
        "common_uses": "Lowering elevated total cholesterol, LDL-C, and triglycerides; reducing cardiovascular disease risk.",
        "how_it_works": "Slows the production of cholesterol in the liver by blocking the enzyme HMG-CoA reductase.",
        "precautions": "Commonly taken once daily in the evening or at bedtime, with or without food.",
        "side_effects": "Mild muscle aches, headache, digestive discomfort, elevated liver enzymes.",
        "warnings": "Notify your doctor immediately if you experience unexplained severe muscle pain or weakness. Avoid excessive grapefruit intake."
    },
    "amlodipine": {
        "generic": "Amlodipine Besylate",
        "category": "Calcium Channel Blocker (Dihydropyridine)",
        "common_uses": "Management of high blood pressure (hypertension) and coronary artery disease / angina.",
        "how_it_works": "Relaxes vascular smooth muscle and widens blood vessels, facilitating smoother blood flow and lowering cardiac workload.",
        "precautions": "Take consistently at the same time each day. Do not stop abruptly without medical guidance.",
        "side_effects": "Swelling in lower legs or ankles (peripheral edema), flushing, fatigue, dizziness.",
        "warnings": "Monitor blood pressure regularly. Avoid rapid changes in posture if feeling dizzy."
    },
    "azithromycin": {
        "generic": "Azithromycin",
        "category": "Macrolide Antibiotic",
        "common_uses": "Bacterial respiratory infections, sinusitis, tonsillitis, and specific soft tissue infections.",
        "how_it_works": "Inhibits bacterial protein synthesis by binding to the 50S ribosomal subunit.",
        "precautions": "Take once daily as directed. May be taken with or without food; taking with food reduces stomach upset.",
        "side_effects": "Nausea, diarrhea, abdominal pain, temporary taste disturbance.",
        "warnings": "Only effective against bacterial, not viral, infections. Report severe watery diarrhea or palpitations."
    },
    "ibuprofen": {
        "generic": "Ibuprofen",
        "category": "Non-Steroidal Anti-Inflammatory Drug (NSAID)",
        "common_uses": "Relief of pain, inflammation, swelling, and fever in arthritis, muscle sprains, and dental pain.",
        "how_it_works": "Inhibits cyclooxygenase enzymes (COX-1 and COX-2) to reduce inflammatory prostaglandin production.",
        "precautions": "Always take with food or milk to minimize gastric irritation.",
        "side_effects": "Heartburn, nausea, indigestion, abdominal discomfort.",
        "warnings": "Caution in patients with peptic ulcers, kidney disease, or uncontrolled hypertension. Not recommended in late pregnancy."
    },
    "cetirizine": {
        "generic": "Cetirizine Hydrochloride",
        "category": "Second-Generation Antihistamine",
        "common_uses": "Allergic rhinitis, hay fever, sneezing, runny nose, itchy watery eyes, and allergic skin hives.",
        "how_it_works": "Selectively blocks peripheral H1 histamine receptors, reducing allergic responses.",
        "precautions": "Often taken once daily at bedtime. May cause mild drowsiness in sensitive individuals.",
        "side_effects": "Mild drowsiness, dry mouth, headache, fatigue.",
        "warnings": "Use caution when driving or operating machinery until individual tolerance is established. Avoid alcohol."
    },
    "telmisartan": {
        "generic": "Telmisartan",
        "category": "Angiotensin II Receptor Blocker (ARB)",
        "common_uses": "Essential hypertension and cardiovascular risk reduction.",
        "how_it_works": "Blocks angiotensin II from binding to vascular receptors, causing vasodilation and reduced vascular resistance.",
        "precautions": "Take once daily. Requires baseline and periodic serum creatinine and potassium checks.",
        "side_effects": "Dizziness, sinus congestion, back pain.",
        "warnings": "Strictly contraindicated during pregnancy. Do not take potassium supplements unless prescribed."
    }
}


# Standard laboratory reference values for educational interpretation
LAB_TEST_REFERENCE_RANGES: Dict[str, Dict[str, Any]] = {
    "hemoglobin": {
        "test_name": "Hemoglobin (Hb)",
        "standard_range": "Men: 13.5 - 17.5 g/dL | Women: 12.0 - 15.5 g/dL",
        "unit": "g/dL",
        "low_meaning": "Lower levels may indicate anemia (nutritional, iron deficiency, chronic illness, blood loss). Causes fatigue or pallor.",
        "high_meaning": "Elevated levels can be seen in dehydration, chronic smoking, high altitude, or polycythemia.",
        "category": "Complete Blood Count (CBC)"
    },
    "wbc": {
        "test_name": "White Blood Cell Count (WBC / TLC)",
        "standard_range": "4,000 - 11,000 /uL (or cells/cumm)",
        "unit": "/uL",
        "low_meaning": "Leukopenia: viral infections, bone marrow suppression, autoimmune conditions, or certain medications.",
        "high_meaning": "Leukocytosis: response to bacterial infection, acute inflammation, physical stress, or steroid medication.",
        "category": "Complete Blood Count (CBC)"
    },
    "platelets": {
        "test_name": "Platelet Count",
        "standard_range": "150,000 - 450,000 /uL",
        "unit": "/uL",
        "low_meaning": "Thrombocytopenia: viral fevers (e.g. dengue), immune conditions, liver disease, or medication effect. Watch for easy bruising.",
        "high_meaning": "Thrombocytosis: reactive inflammation, iron deficiency, or marrow disorders.",
        "category": "Complete Blood Count (CBC)"
    },
    "fasting_glucose": {
        "test_name": "Fasting Blood Sugar (FBS)",
        "standard_range": "Normal: 70 - 99 mg/dL | Pre-diabetes: 100 - 125 mg/dL | Diabetes: >= 126 mg/dL (confirmed on repeat)",
        "unit": "mg/dL",
        "low_meaning": "Hypoglycemia (< 70 mg/dL): excess insulin/medication, prolonged fasting. Causes shakiness, sweating, confusion.",
        "high_meaning": "Hyperglycemia: impaired fasting glucose, insulin resistance, or diabetes mellitus.",
        "category": "Glycemic Profile"
    },
    "hba1c": {
        "test_name": "Glycated Hemoglobin (HbA1c)",
        "standard_range": "Normal: < 5.7% | Pre-diabetes: 5.7% - 6.4% | Diabetes: >= 6.5%",
        "unit": "%",
        "low_meaning": "Reflects low average blood glucose over the past 2-3 months; can be influenced by hemoglobinopathies.",
        "high_meaning": "Indicates elevated average blood glucose over preceding 90 days. Guides diabetic therapy adjustments.",
        "category": "Glycemic Profile"
    },
    "serum_creatinine": {
        "test_name": "Serum Creatinine",
        "standard_range": "0.7 - 1.3 mg/dL (varies with muscle mass and gender)",
        "unit": "mg/dL",
        "low_meaning": "Low muscle mass, severe malnutrition, or normal pregnancy variation.",
        "high_meaning": "Elevated levels suggest reduced kidney filtration efficiency, dehydration, or renal impairment.",
        "category": "Kidney Function Test (KFT)"
    },
    "blood_urea": {
        "test_name": "Blood Urea Nitrogen (BUN) / Blood Urea",
        "standard_range": "7 - 20 mg/dL (BUN) or 15 - 40 mg/dL (Urea)",
        "unit": "mg/dL",
        "low_meaning": "Severe liver disease, low-protein diet, or overhydration.",
        "high_meaning": "Dehydration, high-protein intake, upper GI bleed, or impaired renal clearance.",
        "category": "Kidney Function Test (KFT)"
    },
    "sgpt_alt": {
        "test_name": "SGPT / Alanine Aminotransferase (ALT)",
        "standard_range": "7 - 56 U/L (laboratory specific)",
        "unit": "U/L",
        "low_meaning": "Generally has no clinical significance.",
        "high_meaning": "Suggests liver cell irritation or injury: fatty liver, viral hepatitis, medication effect, alcohol use.",
        "category": "Liver Function Test (LFT)"
    },
    "sgot_ast": {
        "test_name": "SGOT / Aspartate Aminotransferase (AST)",
        "standard_range": "10 - 40 U/L",
        "unit": "U/L",
        "low_meaning": "Generally has no clinical significance.",
        "high_meaning": "Present in liver, cardiac, and skeletal muscle cells. Elevated in liver injury, strenuous exercise, or muscle trauma.",
        "category": "Liver Function Test (LFT)"
    },
    "total_cholesterol": {
        "test_name": "Total Serum Cholesterol",
        "standard_range": "Desirable: < 200 mg/dL | Borderline: 200 - 239 mg/dL | High: >= 240 mg/dL",
        "unit": "mg/dL",
        "low_meaning": "Severe malnutrition or hyperthyroidism.",
        "high_meaning": "Elevated cardiovascular and atherogenic risk. Managed through diet, exercise, and lipid-lowering therapy.",
        "category": "Lipid Profile"
    },
    "tsh": {
        "test_name": "Thyroid Stimulating Hormone (TSH)",
        "standard_range": "0.4 - 4.5 uIU/mL (mIU/L)",
        "unit": "uIU/mL",
        "low_meaning": "Suggests overactive thyroid (Hyperthyroidism) or excess thyroid hormone replacement.",
        "high_meaning": "Suggests underactive thyroid (Hypothyroidism); pituitary attempts to stimulate thyroid gland.",
        "category": "Thyroid Profile"
    }
}


# Radiologic and X-Ray terminology explanations
RADIOLOGY_GLOSSARY: Dict[str, str] = {
    "degenerative changes": "Gradual wear-and-tear in joints or vertebral discs over time (e.g. osteoarthritis), common with aging or repetitive use.",
    "osteophytes": "Small, smooth bony projections ('bone spurs') that typically develop near joints undergoing wear or friction.",
    "consolidation": "An area within the lung tissue that has filled with liquid or inflammatory exudate instead of air, commonly seen in pneumonia.",
    "opacity": "A lighter or whiter area on the X-ray film where tissue is denser than surrounding air-filled areas.",
    "infiltrate": "An abnormal substance (such as fluid, pus, or blood) that has accumulated in lung tissues.",
    "pleural effusion": "An excess buildup of fluid in the space between the layers of the pleura surrounding the lungs.",
    "cardiomegaly": "The radiographic appearance of an enlarged cardiac silhouette, prompting clinical evaluation of heart function.",
    "scoliosis": "A sideways curvature of the spine rather than a straight alignment.",
    "lordosis": "The natural inward curve of the cervical (neck) or lumbar (lower back) spine; loss of lordosis often reflects muscle spasm.",
    "fracture": "A crack or break in the continuity of a bone.",
    "radiolucency": "A darker zone on X-ray representing less dense structures (such as air or reduced bone mineralization).",
    "soft tissue swelling": "Fluid accumulation or inflammation in tissues overlying or adjacent to bones."
}


# Clinical specialty mapping based on symptom keywords
SYMPTOM_SPECIALTY_MAP = [
    {
        "specialty": "Cardiology",
        "department": "Cardiology",
        "keywords": ["chest pain", "palpitations", "irregular heartbeat", "heart", "chhati", "high bp", "hypertension", "angina", "shortness of breath on lying flat"]
    },
    {
        "specialty": "Dermatology",
        "department": "Dermatology",
        "keywords": ["skin", "rash", "itching", "eczema", "acne", "pimples", "psoriasis", "mole", "boil", "blister", "skin allergy", "redness on skin", "fungal"]
    },
    {
        "specialty": "Orthopedics",
        "department": "Orthopedics",
        "keywords": ["joint pain", "knee pain", "bone", "fracture", "back pain", "arthritis", "shoulder pain", "sprain", "ligament", "swollen joint", "spine"]
    },
    {
        "specialty": "Neurology",
        "department": "Neurology",
        "keywords": ["headache", "migraine", "dizziness", "vertigo", "seizure", "numbness", "tingling", "tremor", "memory loss", "chakkar"]
    },
    {
        "specialty": "Pediatrics",
        "department": "Pediatrics",
        "keywords": ["child", "baby", "infant", "toddler", "pediatric", "vaccination", "growth", "bacha", "newborn"]
    },
    {
        "specialty": "ENT (Otolaryngology)",
        "department": "ENT",
        "keywords": ["ear pain", "hearing loss", "throat pain", "sore throat", "tonsils", "sinus", "nasal blockage", "gala", "kaan", "nak se khoon"]
    },
    {
        "specialty": "Gastroenterology",
        "department": "Gastroenterology",
        "keywords": ["stomach pain", "acid reflux", "gerd", "heartburn", "vomiting", "diarrhea", "constipation", "pet dard", "acidity", "jaundice", "liver"]
    },
    {
        "specialty": "Pulmonology",
        "department": "Pulmonology",
        "keywords": ["cough", "wheezing", "asthma", "bronchitis", "phlegm", "khansi", "saans", "tuberculosis", "breathlessness"]
    },
    {
        "specialty": "Ophthalmology",
        "department": "Ophthalmology",
        "keywords": ["eye pain", "blurred vision", "red eye", "cataract", "dry eyes", "aankh", "vision loss", "watery eyes"]
    },
    {
        "specialty": "General Medicine",
        "department": "General Medicine",
        "keywords": ["fever", "weakness", "fatigue", "body ache", "bukhar", "chills", "malaise", "unexplained weight loss", "viral"]
    }
]
