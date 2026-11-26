from __future__ import annotations

import json
import pickle
import random
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import torch
from imblearn.over_sampling import SMOTE
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    precision_recall_fscore_support,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelBinarizer, StandardScaler
from torch import nn
from torch.utils.data import DataLoader, TensorDataset


DATA_DIR = Path(__file__).resolve().parent
DATA_PATH = DATA_DIR / "nutrition_selected_final.csv"
OUTPUT_DIR = DATA_DIR / "outputs"
EDA_DIR = OUTPUT_DIR / "eda"
MODEL_DIR = OUTPUT_DIR / "model"
REPORT_PATH = OUTPUT_DIR / "nova_model_report.json"

TARGET_COLUMN = "nova-group_100g"
FEATURE_COLUMNS = [
    "energy-kcal_100g",
    "fat_100g",
    "saturated-fat_100g",
    "carbohydrates_100g",
    "sugars_100g",
    "fiber_100g",
    "proteins_100g",
    "salt_100g",
    "sodium_100g",
    "nutrition-score-fr_100g",
]
LABEL_NAMES = {1: "NOVA 1", 2: "NOVA 2", 3: "NOVA 3", 4: "NOVA 4"}


def set_seed(seed: int = 42) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def ensure_dirs() -> None:
    EDA_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)


def save_plot(fig, path: Path) -> None:
    fig.tight_layout()
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def build_eda(df: pd.DataFrame) -> None:
    summary = {
        "rows": int(df.shape[0]),
        "columns": int(df.shape[1]),
        "target_column": TARGET_COLUMN,
        "target_distribution": df[TARGET_COLUMN].value_counts().sort_index().astype(int).to_dict(),
        "feature_count": len(FEATURE_COLUMNS),
        "missing_values": {
            key: float(value)
            for key, value in df[FEATURE_COLUMNS].isna().mean().sort_values(ascending=False).items()
        },
        "duplicated_rows": int(df.duplicated().sum()),
    }
    (OUTPUT_DIR / "eda_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    fig, ax = plt.subplots(figsize=(8, 5))
    sns.countplot(data=df, x=TARGET_COLUMN, hue=TARGET_COLUMN, palette="viridis", ax=ax, dodge=False, legend=False)
    ax.set_title("NOVA class distribution")
    ax.set_xlabel("NOVA group")
    ax.set_ylabel("Count")
    save_plot(fig, EDA_DIR / "nova_class_distribution.png")

    missing_df = df[FEATURE_COLUMNS].isna().mean().sort_values(ascending=False).reset_index()
    missing_df.columns = ["feature", "missing_ratio"]
    fig, ax = plt.subplots(figsize=(10, 6))
    sns.barplot(data=missing_df, x="missing_ratio", y="feature", hue="feature", palette="mako", ax=ax, dodge=False, legend=False)
    ax.set_title("Feature missingness")
    ax.set_xlabel("Missing ratio")
    ax.set_ylabel("Feature")
    save_plot(fig, EDA_DIR / "feature_missingness.png")

    selected = ["energy-kcal_100g", "fat_100g", "carbohydrates_100g", "proteins_100g", "sugars_100g"]
    valid = [c for c in selected if c in df.columns]
    if valid:
        fig, axes = plt.subplots(len(valid), 2, figsize=(14, 4 * len(valid)))
        for idx, col in enumerate(valid):
            sns.histplot(df[col].dropna(), bins=40, kde=True, ax=axes[idx, 0])
            axes[idx, 0].set_title(f"Distribution of {col}")
            sns.boxplot(x=df[TARGET_COLUMN], y=df[col], data=df, ax=axes[idx, 1])
            axes[idx, 1].set_title(f"{col} by NOVA class")
        save_plot(fig, EDA_DIR / "feature_distribution_and_boxplots.png")

    corr = df[FEATURE_COLUMNS].corr(numeric_only=True)
    fig, ax = plt.subplots(figsize=(12, 10))
    sns.heatmap(corr, annot=False, cmap="coolwarm", center=0, ax=ax)
    ax.set_title("Feature correlation heatmap")
    save_plot(fig, EDA_DIR / "feature_correlation_heatmap.png")

    fig, ax = plt.subplots(figsize=(10, 6))
    sns.violinplot(data=df, x=TARGET_COLUMN, y="nutrition-score-fr_100g", hue=TARGET_COLUMN, palette="viridis", ax=ax, dodge=False, legend=False)
    ax.set_title("Nutrition score by NOVA class")
    save_plot(fig, EDA_DIR / "nutrition_score_by_nova.png")


def build_model(input_dim: int, hidden_dims: tuple[int, ...] = (128, 64), dropout: float = 0.2) -> nn.Module:
    layers: list[nn.Module] = []
    prev_dim = input_dim
    for hidden_dim in hidden_dims:
        layers.extend([nn.Linear(prev_dim, hidden_dim), nn.ReLU(), nn.Dropout(dropout)])
        prev_dim = hidden_dim
    layers.append(nn.Linear(prev_dim, 4))
    return nn.Sequential(*layers)


def evaluate_model(model: nn.Module, loader: DataLoader, device: torch.device) -> tuple[float, float, np.ndarray, np.ndarray, np.ndarray]:
    model.eval()
    total_loss = 0.0
    total_count = 0
    all_preds: list[int] = []
    all_targets: list[int] = []
    all_probs: list[np.ndarray] = []
    criterion = nn.CrossEntropyLoss()

    with torch.no_grad():
        for xb, yb in loader:
            xb = xb.to(device)
            yb = yb.to(device)
            logits = model(xb)
            loss = criterion(logits, yb)
            total_loss += loss.item() * yb.size(0)
            total_count += yb.size(0)
            probs = torch.softmax(logits, dim=1).cpu().numpy()
            preds = probs.argmax(axis=1)
            all_preds.extend(preds.tolist())
            all_targets.extend(yb.cpu().numpy().tolist())
            all_probs.extend(probs)

    mean_loss = total_loss / max(total_count, 1)
    acc = accuracy_score(np.asarray(all_targets), np.asarray(all_preds))
    return mean_loss, acc, np.asarray(all_targets), np.asarray(all_preds), np.asarray(all_probs)


def apply_probability_thresholds(probs: np.ndarray, thresholds: list[float]) -> np.ndarray:
    probs = np.asarray(probs, dtype=np.float32)
    pred = probs.argmax(axis=1)
    for idx, row in enumerate(probs):
        best_idx = int(row.argmax())
        best_prob = float(row[best_idx])
        if best_prob < thresholds[best_idx]:
            eligible = np.where(row >= np.asarray(thresholds, dtype=np.float32))[0]
            if eligible.size:
                pred[idx] = int(eligible[np.argmax(row[eligible])])
            else:
                pred[idx] = best_idx
    return pred


def tune_probability_thresholds(y_true: np.ndarray, probabilities: np.ndarray) -> list[float]:
    candidate_thresholds = [0.35, 0.45, 0.55, 0.65, 0.75]
    best_score = -np.inf
    best_thresholds = [0.5, 0.5, 0.5, 0.5]
    for thresholds in np.array(np.meshgrid(*[candidate_thresholds] * 4)).T.reshape(-1, 4):
        pred = apply_probability_thresholds(probabilities, thresholds.tolist())
        acc = accuracy_score(y_true, pred)
        macro_precision = precision_score(y_true, pred, average="macro", zero_division=0)
        score = acc + 0.5 * macro_precision
        if score > best_score:
            best_score = score
            best_thresholds = thresholds.tolist()
    return best_thresholds


class TorchModelWrapper:
    def __init__(self, model: nn.Module, device: torch.device):
        self.model = model.to(device)
        self.device = device

    def fit(self, X, y):
        return self

    def predict(self, X):
        X_t = torch.tensor(np.asarray(X, dtype=np.float32), device=self.device)
        with torch.no_grad():
            logits = self.model(X_t)
        return logits.argmax(dim=1).cpu().numpy()

    def predict_proba(self, X):
        X_t = torch.tensor(np.asarray(X, dtype=np.float32), device=self.device)
        with torch.no_grad():
            logits = self.model(X_t)
        return torch.softmax(logits, dim=1).cpu().numpy()


def save_confusion_matrix(y_true: np.ndarray, y_pred: np.ndarray, labels: list[int]) -> None:
    fig, ax = plt.subplots(figsize=(8, 7))
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    sns.heatmap(cm, annot=True, fmt="d", cmap="Blues", xticklabels=[LABEL_NAMES[l] for l in labels], yticklabels=[LABEL_NAMES[l] for l in labels], ax=ax)
    ax.set_xlabel("Predicted label")
    ax.set_ylabel("True label")
    ax.set_title("Confusion matrix")
    save_plot(fig, EDA_DIR / "confusion_matrix.png")

    metrics = {
        "confusion_matrix": cm.astype(int).tolist(),
        "labels": labels,
    }
    (OUTPUT_DIR / "confusion_matrix.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")


def save_training_curves(history: dict[str, list[float]]) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    axes[0].plot(history["train_loss"], label="Train loss")
    axes[0].plot(history["val_loss"], label="Validation loss")
    axes[0].set_title("Train vs validation loss")
    axes[0].set_xlabel("Epoch")
    axes[0].set_ylabel("Loss")
    axes[0].legend()

    axes[1].plot(history["train_accuracy"], label="Train accuracy")
    axes[1].plot(history["val_accuracy"], label="Validation accuracy")
    axes[1].set_title("Train vs validation accuracy")
    axes[1].set_xlabel("Epoch")
    axes[1].set_ylabel("Accuracy")
    axes[1].legend()
    save_plot(fig, EDA_DIR / "training_history.png")


def main() -> None:
    set_seed(42)
    ensure_dirs()

    df = pd.read_csv(DATA_PATH)
    df.columns = [str(col).strip() for col in df.columns]
    df = df.drop_duplicates().copy()

    df[TARGET_COLUMN] = pd.to_numeric(df[TARGET_COLUMN], errors="coerce")
    df = df[df[TARGET_COLUMN].isin([1, 2, 3, 4])].copy()
    df[TARGET_COLUMN] = df[TARGET_COLUMN].astype(int)
    df = df[FEATURE_COLUMNS + [TARGET_COLUMN]].copy()

    build_eda(df)

    X = df[FEATURE_COLUMNS].copy()
    y = (df[TARGET_COLUMN].astype(int) - 1).to_numpy()

    X_train, X_temp, y_train, y_temp = train_test_split(
        X,
        y,
        test_size=0.30,
        random_state=42,
        stratify=y,
    )
    X_val, X_test, y_val, y_test = train_test_split(
        X_temp,
        y_temp,
        test_size=0.50,
        random_state=42,
        stratify=y_temp,
    )

    imputer = SimpleImputer(strategy="median")
    X_train_imputed = imputer.fit_transform(X_train)
    X_val_imputed = imputer.transform(X_val)
    X_test_imputed = imputer.transform(X_test)
    with open(MODEL_DIR / "imputer.pkl", "wb") as fh:
        pickle.dump(imputer, fh)

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train_imputed)
    X_val_scaled = scaler.transform(X_val_imputed)
    X_test_scaled = scaler.transform(X_test_imputed)
    with open(MODEL_DIR / "scaler.pkl", "wb") as fh:
        pickle.dump(scaler, fh)

    smote = SMOTE(random_state=42, k_neighbors=3)
    X_train_bal, y_train_bal = smote.fit_resample(X_train_scaled, y_train)

    before = pd.Series(y_train + 1).value_counts().sort_index()
    after = pd.Series(y_train_bal + 1).value_counts().sort_index()
    balance_df = pd.DataFrame({"before": before, "after": after}).fillna(0).astype(int)
    fig, ax = plt.subplots(figsize=(8, 5))
    balance_df.plot(kind="bar", ax=ax)
    ax.set_title("Class distribution before vs after SMOTE")
    ax.set_xlabel("NOVA class")
    ax.set_ylabel("Count")
    save_plot(fig, EDA_DIR / "smote_class_distribution.png")
    balance_df.to_csv(OUTPUT_DIR / "smote_distribution.csv")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = build_model(input_dim=X_train_bal.shape[1]).to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode="min", factor=0.5, patience=3)

    train_dataset = TensorDataset(torch.tensor(X_train_bal, dtype=torch.float32), torch.tensor(y_train_bal, dtype=torch.long))
    val_dataset = TensorDataset(torch.tensor(X_val_scaled, dtype=torch.float32), torch.tensor(y_val, dtype=torch.long))
    train_loader = DataLoader(train_dataset, batch_size=256, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=512, shuffle=False)

    history = {"train_loss": [], "val_loss": [], "train_accuracy": [], "val_accuracy": []}
    best_state = None
    best_val_loss = float("inf")
    patience = 0
    epochs = 20

    for epoch in range(1, epochs + 1):
        model.train()
        running_loss = 0.0
        running_correct = 0
        running_total = 0
        for xb, yb in train_loader:
            xb = xb.to(device)
            yb = yb.to(device)
            optimizer.zero_grad()
            logits = model(xb)
            loss = criterion(logits, yb)
            loss.backward()
            optimizer.step()

            running_loss += loss.item() * yb.size(0)
            preds = logits.argmax(dim=1)
            running_correct += (preds == yb).sum().item()
            running_total += yb.size(0)

        train_loss = running_loss / max(running_total, 1)
        train_acc = running_correct / max(running_total, 1)
        val_loss, val_acc, _, _, _ = evaluate_model(model, val_loader, device)
        scheduler.step(val_loss)

        history["train_loss"].append(train_loss)
        history["val_loss"].append(val_loss)
        history["train_accuracy"].append(train_acc)
        history["val_accuracy"].append(val_acc)

        if val_loss < best_val_loss - 1e-4:
            best_val_loss = val_loss
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            patience = 0
        else:
            patience += 1
            if patience >= 5:
                break

    if best_state is not None:
        model.load_state_dict(best_state)
    save_training_curves(history)

    val_loss, val_acc, y_val_true, _, y_val_prob = evaluate_model(model, val_loader, device)
    val_thresholds = tune_probability_thresholds(y_val_true, y_val_prob)
    (OUTPUT_DIR / "validation_thresholds.json").write_text(json.dumps({"thresholds": val_thresholds}), encoding="utf-8")

    torch.save(
        {
            "state_dict": model.state_dict(),
            "feature_columns": FEATURE_COLUMNS,
            "labels": [1, 2, 3, 4],
            "history": history,
        },
        MODEL_DIR / "nova_classifier.pt",
    )

    test_loader = DataLoader(TensorDataset(torch.tensor(X_test_scaled, dtype=torch.float32), torch.tensor(y_test, dtype=torch.long)), batch_size=512, shuffle=False)
    _, test_acc, y_true, _, y_prob = evaluate_model(model, test_loader, device)
    y_pred = apply_probability_thresholds(y_prob, val_thresholds)
    labels = [0, 1, 2, 3]
    orig_y_true = y_true + 1
    orig_y_pred = y_pred + 1
    test_acc = accuracy_score(orig_y_true, orig_y_pred)
    precision, recall, f1, _ = precision_recall_fscore_support(orig_y_true, orig_y_pred, labels=[1, 2, 3, 4], average=None, zero_division=0)
    macro_f1 = f1_score(orig_y_true, orig_y_pred, average="macro", labels=[1, 2, 3, 4])
    weighted_f1 = f1_score(orig_y_true, orig_y_pred, average="weighted", labels=[1, 2, 3, 4])
    balanced_acc = balanced_accuracy_score(orig_y_true, orig_y_pred)
    majority_accuracy = pd.Series(y_test + 1).value_counts(normalize=True).max()

    lb = LabelBinarizer().fit(orig_y_true)
    y_true_onehot = lb.transform(orig_y_true)
    roc_auc = roc_auc_score(y_true_onehot, np.asarray(y_prob), multi_class="ovr", average="macro")

    report = classification_report(
        orig_y_true,
        orig_y_pred,
        labels=[1, 2, 3, 4],
        target_names=[LABEL_NAMES[label] for label in [1, 2, 3, 4]],
        output_dict=True,
        zero_division=0,
    )
    metrics = {
        "accuracy": float(test_acc),
        "balanced_accuracy": float(balanced_acc),
        "macro_f1": float(macro_f1),
        "weighted_f1": float(weighted_f1),
        "per_class": {
            str(label): {
                "precision": float(precision[idx]),
                "recall": float(recall[idx]),
                "f1": float(f1[idx]),
            }
            for idx, label in enumerate([1, 2, 3, 4])
        },
        "roc_auc_macro_ovr": float(roc_auc),
        "baseline_majority_accuracy": float(majority_accuracy),
        "classification_report": report,
    }
    REPORT_PATH.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    save_confusion_matrix(orig_y_true, orig_y_pred, [1, 2, 3, 4])

    wrapper = TorchModelWrapper(model, device)

    def custom_f1_weighted(estimator, X, y):
        pred = estimator.predict(X)
        return f1_score(y, pred, average="weighted")

    perm = permutation_importance(wrapper, X_test_scaled, y_test, n_repeats=5, random_state=42, scoring=custom_f1_weighted)
    importance_df = pd.DataFrame(
        {"feature": FEATURE_COLUMNS, "importance_mean": perm.importances_mean, "importance_std": perm.importances_std}
    ).sort_values("importance_mean", ascending=False)
    importance_df.to_csv(OUTPUT_DIR / "feature_importance.csv", index=False)

    fig, ax = plt.subplots(figsize=(10, 6))
    sns.barplot(data=importance_df, x="importance_mean", y="feature", palette="viridis", ax=ax)
    ax.set_title("Permutation importance by feature")
    ax.set_xlabel("Mean F1-weighted decrease")
    ax.set_ylabel("Feature")
    save_plot(fig, EDA_DIR / "feature_importance.png")

    print(json.dumps({
        "accuracy": round(float(test_acc), 4),
        "balanced_accuracy": round(float(balanced_acc), 4),
        "macro_f1": round(float(macro_f1), 4),
        "weighted_f1": round(float(weighted_f1), 4),
        "baseline_majority_accuracy": round(float(majority_accuracy), 4),
        "roc_auc_macro_ovr": round(float(roc_auc), 4),
        "model_path": str(MODEL_DIR / "nova_classifier.pt"),
    }, indent=2))


if __name__ == "__main__":
    main()
