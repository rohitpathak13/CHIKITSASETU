"""
CLI Orchestrator for retraining all Machine Learning models.
Usage: python -m scripts.train_all_models
"""
from ml.train.train_readmission import train as train_readmission
from ml.train.train_no_show import train as train_no_show

def main():
    print("==================================================")
    print(" MediCare AI - Retraining All Predictive ML Models ")
    print("==================================================")
    train_readmission()
    print("--------------------------------------------------")
    train_no_show()
    print("==================================================")
    print(" [✓] All models successfully retrained and saved! ")
    print("==================================================")

if __name__ == "__main__":
    main()
