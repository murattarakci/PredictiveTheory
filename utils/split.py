import pandas as pd
from sklearn.model_selection import train_test_split

def split_dataset(file_path: str, output_dir: str):
    df = pd.read_csv(file_path)

    train, temp = train_test_split(df, test_size=0.4, random_state=42)
    val, test = train_test_split(temp, test_size=0.5, random_state=42)

    train.to_csv(f"{output_dir}/train.csv", index=False)
    test.to_csv(f"{output_dir}/test.csv", index=False)
    val.to_csv(f"{output_dir}/validation.csv", index=False)
