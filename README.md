A maintained version of Anthropic’s token estimator Jupyter notebook.

The context feature is in: you can paste the conversation so far alongside the prompt you want to add, and the notebook prices the prompt as the next turn of a real conversation rather than in a vacuum. Because the Messages API is stateless, every prior turn is resent and re-billed on every request, so it also shows how much of each turn is just re-sending context, projects the cost of the next N turns as the conversation grows, and estimates what prompt caching would save.

Still on the list: supporting other AI providers.
