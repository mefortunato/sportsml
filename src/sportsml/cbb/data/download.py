from .kaggle import download_kaggle


def download(output_file: str = None, year: int = 2026):
    """Men's games from Kaggle's March Machine Learning Mania ``year``."""
    return download_kaggle("M", year, output_file)
