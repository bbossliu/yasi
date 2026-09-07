def accuracy_to_band(acc: float) -> float:
    """听力正确率(0-100) → band"""
    if acc < 40: return 4.5
    if acc < 55: return 5.0
    if acc < 70: return 5.5
    if acc < 80: return 6.0
    if acc < 90: return 6.5
    if acc < 95: return 7.0
    return 7.5


def vocab_rate_to_band(rate: float) -> float:
    """词汇掌握率(0-1) → band"""
    if rate < 0.5: return 5.0
    if rate < 0.7: return 5.5
    if rate < 0.85: return 6.0
    if rate < 0.95: return 6.5
    return 7.0


def overall_round(avg: float) -> float:
    """雅思官方均分取整：.25 进 .5，.75 进下一整分"""
    whole = int(avg)
    frac = avg - whole
    if frac < 0.25:
        return float(whole)
    if frac < 0.75:
        return whole + 0.5
    return float(whole + 1)
