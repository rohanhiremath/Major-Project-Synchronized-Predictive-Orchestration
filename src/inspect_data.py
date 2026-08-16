import pandas as pd

FILE = "data/ptcs_training_data_full_psi.csv"

df = pd.read_csv(FILE)

df["timestamp"] = pd.to_datetime(df["timestamp"])

print("=" * 60)
print("DATASET INFORMATION")
print("=" * 60)

print("Shape:", df.shape)

print("\nColumns:")
for column in df.columns:
    print(" -", column)

print("\nMissing values:")
print(df.isnull().sum())

print("\nDuplicate timestamps:")
print(df["timestamp"].duplicated().sum())

print("\nTime range:")
print("Start:", df["timestamp"].min())
print("End:  ", df["timestamp"].max())

print("\nSampling intervals:")
print(
    df["timestamp"]
    .diff()
    .dt.total_seconds()
    .value_counts()
    .sort_index()
)

print("\nStatistics:")
print(df.describe())

print("\nFirst 5 rows:")
print(df.head())
