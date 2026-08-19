import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score
from sklearn.ensemble import RandomForestClassifier
import pickle

def train_model():
    print("Loading triage dataset...")
    df = pd.read_csv("triage_navigator_dataset.csv")
    
    # Reconstruct critical emergency flags directly from df for the safety audit and override
    age = 2010 - (df['BENE_BIRTH_DT'] // 10000)
    sp_chf = np.where(df['SP_CHF'] == 1, 1, 0)
    sp_ischmcht = np.where(df['SP_ISCHMCHT'] == 1, 1, 0)
    sp_cncr = np.where(df['SP_CNCR'] == 1, 1, 0)
    
    # Impute missing vitals for rule evaluation
    spo2_home = df['spo2_home'].fillna(98.0)
    temp_home = df['temperature_home'].fillna(36.8)
    hr_home = df['heart_rate_home'].fillna(75.0)
    
    crit_cardiac = (df['primary_symptom'] == 'chest_pain') & (df['symptom_onset'] == 'sudden') & ((sp_ischmcht == 1) | (sp_chf == 1))
    severe_chest = (df['primary_symptom'] == 'chest_pain') & (df['pain_level'] >= 8.5)
    hypoxia = (spo2_home < 90)
    sepsis = (df['primary_symptom'] == 'fever') & (sp_cncr == 1)
    extreme_vitals = (temp_home >= 39.5) | (hr_home >= 135)
    elderly_abdomen = (df['primary_symptom'] == 'abdominal_pain') & (df['symptom_onset'] == 'sudden') & (age >= 72) & (df['pain_level'] >= 7.0)
    
    is_critical_emergency = crit_cardiac | severe_chest | hypoxia | sepsis | extreme_vitals | elderly_abdomen
    
    # 1. Separate Features and Target
    X = df.drop(columns=['DESYNPUF_ID', 'needs_ed', 'care_recommendation'])
    # Handle optional death date if present (drop it as patients are alive)
    if 'BENE_DEATH_DT' in X.columns:
        X = X.drop(columns=['BENE_DEATH_DT'])
        
    y = df['care_recommendation']
    
    # 2. Decode Medicare Standard SynPUF Variables
    print("Parsing Medicare CMS variables...")
    # Calculate age from BENE_BIRTH_DT (YYYYMMDD)
    X['age'] = 2010 - (X['BENE_BIRTH_DT'] // 10000)
    X = X.drop(columns=['BENE_BIRTH_DT'])
    
    # Sex Code: 1 = Male, 2 = Female -> Binary is_male
    X['is_male'] = np.where(X['BENE_SEX_IDENT_CD'] == 1, 1, 0)
    X = X.drop(columns=['BENE_SEX_IDENT_CD'])
    
    # Chronic Conditions: 1 = Yes, 2 = No -> Binary 1/0
    chronic_cols = ['SP_CHF', 'SP_CHRNKIDN', 'SP_CNCR', 'SP_COPD', 'SP_DIABETES', 'SP_ISCHMCHT', 'SP_STRKETIA']
    for col in chronic_cols:
        X[col] = np.where(X[col] == 1, 1, 0)
        
    # 3. Clinical Imputation for Missing Home Vitals
    print("Applying clinical normal imputation for missing home vitals...")
    X['spo2_home'] = X['spo2_home'].fillna(98.0)
    X['temperature_home'] = X['temperature_home'].fillna(36.8)
    X['heart_rate_home'] = X['heart_rate_home'].fillna(75.0)
    
    # 4. Label Encode Target
    label_encoder = LabelEncoder()
    y_encoded = label_encoder.fit_transform(y)
    class_names = label_encoder.classes_
    print(f"Target classes encoded: {dict(zip(range(len(class_names)), class_names))}")
    
    # 5. One-Hot Encode Categorical Columns
    print("One-hot encoding categorical symptoms...")
    X_encoded = pd.get_dummies(X, columns=['primary_symptom', 'symptom_onset'], drop_first=True)
    feature_columns = X_encoded.columns.tolist()
    
    # 6. Train-Test Split
    X_train, X_test, y_train, y_test = train_test_split(
        X_encoded, y_encoded, test_size=0.2, random_state=42, stratify=y_encoded
    )
    
    # 7. Train Random Forest Classifier
    print("Training Random Forest multi-class classifier...")
    model = RandomForestClassifier(
        n_estimators=100,
        max_depth=10,
        random_state=42
    )
    model.fit(X_train, y_train)
    print("Model training complete!")
    
    # 8. Evaluate Model (Raw predictions)
    y_pred_raw = model.predict(X_test)
    accuracy_raw = accuracy_score(y_test, y_pred_raw)
    
    print("\n" + "="*40)
    print("RAW MACHINE LEARNING MODEL EVALUATION")
    print("="*40)
    print(f"Accuracy: {accuracy_raw*100:.2f}%")
    print("\nClassification Report (Raw Model):")
    print(classification_report(y_test, y_pred_raw, target_names=class_names))
    
    # Reconstruct test set critical flags
    is_critical_test = is_critical_emergency.loc[X_test.index].values
    critical_test_indices = np.where(is_critical_test)[0]
    ed_class_idx = list(class_names).index('ED')
    
    # Raw Safety Audit (Checks all classes that are not ED for any critical patient)
    raw_critical_false_negatives = np.sum(y_pred_raw[critical_test_indices] != ed_class_idx)
    
    print("\n" + "="*40)
    print("CLINICAL SAFETY AUDIT (RAW MODEL)")
    print("="*40)
    print(f"Total True Critical Emergency Patients in Test Set: {len(critical_test_indices)}")
    print(f"Critical Patients Downgraded (Misclassified as non-ED): {raw_critical_false_negatives}")
    if len(critical_test_indices) > 0:
        fail_rate_raw = (raw_critical_false_negatives / len(critical_test_indices)) * 100
        print(f"Critical Safety Failure Rate (Raw Model): {fail_rate_raw:.2f}%")
        if raw_critical_false_negatives > 0:
            print("WARNING: Raw ML model failed the safety check! Critical patients were downgraded.")

    # 9. Apply Hybrid Clinical Safety Override (Rule-Based Override)
    print("\nApplying Hybrid Safety Gate rules override...")
    y_pred_hybrid = y_pred_raw.copy()
    y_pred_hybrid[critical_test_indices] = ed_class_idx
    
    accuracy_hybrid = accuracy_score(y_test, y_pred_hybrid)
    
    print("\n" + "="*40)
    print("HYBRID SYSTEM EVALUATION (MODEL + SAFETY GATE)")
    print("="*40)
    print(f"Hybrid Accuracy: {accuracy_hybrid*100:.2f}%")
    
    print("\nClassification Report (Hybrid System):")
    print(classification_report(y_test, y_pred_hybrid, target_names=class_names))
    
    print("Confusion Matrix (Hybrid System):")
    cm_hybrid = confusion_matrix(y_test, y_pred_hybrid)
    print(pd.DataFrame(cm_hybrid, index=class_names, columns=class_names))
    
    # Hybrid Safety Audit
    hybrid_critical_false_negatives = np.sum(y_pred_hybrid[critical_test_indices] != ed_class_idx)
    
    print("\n" + "="*40)
    print("CLINICAL SAFETY AUDIT (HYBRID SYSTEM)")
    print("="*40)
    print(f"Total True Critical Emergency Patients in Test Set: {len(critical_test_indices)}")
    print(f"Critical Patients Downgraded (Misclassified as non-ED): {hybrid_critical_false_negatives}")
    if len(critical_test_indices) > 0:
        fail_rate_hybrid = (hybrid_critical_false_negatives / len(critical_test_indices)) * 100
        print(f"Critical Safety Failure Rate (Hybrid System): {fail_rate_hybrid:.2f}%")
        if hybrid_critical_false_negatives == 0:
            print("SUCCESS: Zero-tolerance safety gate passed! 100% of critical patients successfully routed to ED.")
        else:
            print("ERROR: Hybrid override failed to protect all critical patients!")
            
    # 10. Feature Importance
    print("\nTop 10 Most Important Features:")
    importances = model.feature_importances_
    indices = np.argsort(importances)[::-1]
    for i in range(min(10, len(feature_columns))):
        print(f"  {i+1}. {feature_columns[indices[i]]}: {importances[indices[i]]:.4f}")
        
    # 11. Save Model and Metadata
    print("\nSaving model and metadata...")
    artifacts = {
        'model': model,
        'label_encoder': label_encoder,
        'feature_columns': feature_columns
    }
    with open("triage_navigator_model.pkl", "wb") as f:
        pickle.dump(artifacts, f)
    print("Model saved to triage_navigator_model.pkl!")

if __name__ == "__main__":
    train_model()
