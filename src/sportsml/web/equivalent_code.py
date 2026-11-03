"""Code hashes whose backtests are the same as an older code's.

A change to hashed source (:func:`sportsml.web.build.code_hash`) gives
every sport new backtest keys, even when it changes the results of only
some sports. Mapping a sport's new hash to the old one here lets a build
reuse the seasons stored under the old keys (and store them again under
the new ones) instead of backtesting them again.

The map is keyed by the new hash, so it applies only to exactly that
source: any later change to hashed code makes it inert. This module is
under ``web/`` and so not hashed itself. Add an entry only when the
change leaves that sport's walk-forward results identical.
"""

from __future__ import annotations

EQUIVALENT_CODE: dict[str, tuple[str, ...]] = {
    # Weekly power rankings for college basketball (``ranking_every``):
    # every other sport still ranks before every date.
    # nfl
    "50980762340fa398b8c04386da83f199afedd90af5faa51104ef4e93fe16a912": (
        "9f8bdd5b6fe3111ee009e08c0e54bedd127ad0c59cb42c0e9d8465eb08db684d",
    ),
    # cfb
    "eff9b39d7ae37ec41e4d2c8fd83cbaef6f777fa4cfae5a1123db92bc81805848": (
        "3fcdd4044659df88f9f195100a1708ef40794e8b8b059056df1de39151b5cea9",
    ),
    # nba
    "260ececb2f697adb265f585b85de761600bcf794bd6291c3ed9671fd4fb942c5": (
        "e0e6dc1367a80f3c528254c80fcd0a741f377f4966e0cdc4abc9b7e49c100ac6",
    ),
    # wnba
    "5bb3845830ac4637acc7564e812cc4382a960c8b75e421230a2a8a2bc4c0a16e": (
        "5f3572bf56b9d982c22886186910b1f2bb5e9a70ed57aeef20499266ec33af2b",
    ),
    # nhl
    "9ae5b3c7bb86381199f4bbfb219794dba2ebbc82ce9c6c30551cf9e49a7a8c84": (
        "f1b5541a229ceaf439d50e8b4336daa2ce3d42312979c7ac431b115126a9fc6e",
    ),
    # mlb
    "655a3e7adab6353b1791d92903d2c2b1c3203a69cf0b375e90ecc4a94f606d26": (
        "8158c871cd70aabecfa85bd55019e1c18a2e199ae98a4557db53f62e95c2342c",
    ),
}
