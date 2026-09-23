"""
Jordanian macroeconomic context used to ground AI-generated advice in
real-world market conditions.

Kept as plain constants for now -- there's no live feed wired up yet, so
these are illustrative, roughly current figures for the Jordanian economy.
Revisit if/when a real data source (e.g. Central Bank of Jordan API) is
integrated.
"""

from finance import CENTRAL_BANK_POLICY_RATE

# Central Bank of Jordan policy rate, reused from finance.py so both modules
# stay in sync if the rate is ever updated.
CBJ_POLICY_RATE_PERCENT = CENTRAL_BANK_POLICY_RATE * 100  # 7.25%

# Illustrative annual inflation rate (CPI, year-over-year).
INFLATION_RATE_PERCENT = 3.8

# Illustrative foreign currency reserves held by the Central Bank of Jordan.
FOREX_RESERVES_USD_BILLION = 18.2


def get_market_headlines() -> list[str]:
    """
    Return a handful of current Jordanian market headlines (Arabic), built
    from the constants above, for grounding AI-generated financial advice.
    """
    return [
        f"سعر الفائدة الرئيسي للبنك المركزي الأردني حاليًا عند {CBJ_POLICY_RATE_PERCENT:.2f}%.",
        f"معدل التضخم السنوي في الأردن يقارب {INFLATION_RATE_PERCENT:.1f}%.",
        f"احتياطيات العملات الأجنبية لدى البنك المركزي الأردني تبلغ نحو {FOREX_RESERVES_USD_BILLION:.1f} مليار دولار.",
    ]
