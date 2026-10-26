from ...cbb.data.kaggle import download_kaggle


def download(output_file: str = None, year: int = 2026):
    """Women's games from Kaggle's March Machine Learning Mania ``year``."""
    return download_kaggle("W", year, output_file)
