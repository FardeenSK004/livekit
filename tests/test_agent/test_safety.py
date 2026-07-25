from app.agent.safety import SafetyMonitor


def test_is_farewell_detects_goodbye():
    assert SafetyMonitor.is_farewell("Thank you for calling, goodbye!")
    assert SafetyMonitor.is_farewell("Have a great day")
    assert not SafetyMonitor.is_farewell("How can I help you today?")
