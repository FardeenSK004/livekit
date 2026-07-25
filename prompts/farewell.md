Detect when the agent is saying goodbye without calling end_call.
Farewell phrases that trigger the safety net:
goodbye, good bye, bye bye, take care, have a great day, have a good day,
have a nice day, thanks for calling, thank you for calling, talk to you later,
see you later.

If detected and end_call was never invoked, force-disconnect after TTS finishes.
