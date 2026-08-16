import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("data/ptcs_training_data_full_psi.csv")

df["timestamp"] = pd.to_datetime(df["timestamp"])
df = df.sort_values("timestamp")

columns = [
    "cpu_usage",
    "memory_usage",
    "read_bytes_per_sec",
    "write_bytes_per_sec",
    "psi_some_avg10",
    "psi_some_avg60",
    "psi_some_avg300",
    "psi_full_avg10",
    "psi_full_avg60",
    "psi_full_avg300",
]

for column in columns:
    plt.figure(figsize=(12, 5))

    plt.plot(df["timestamp"], df[column])

    plt.title(column)
    plt.xlabel("Time")
    plt.ylabel(column)

    plt.xticks(rotation=45)
    plt.tight_layout()

    plt.savefig(f"results/{column}.png")
    plt.close()
