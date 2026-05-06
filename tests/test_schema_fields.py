def test_trading_state_has_jury_fields():
    from src.state.schema import TradingState
    hints = TradingState.__annotations__
    assert "risk_manager_vote" in hints
    assert "quant_vote" in hints
    assert "behavioral_skeptic_vote" in hints
