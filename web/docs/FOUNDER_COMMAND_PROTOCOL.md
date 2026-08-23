# Founder command protocol

The founder command path is intentionally small. A browser can request only one of the fixed, parameter-free actions, and the outbound agent can only move that request through the reviewed state machine.

Transport acknowledgement is not treated as proof that a database write did or did not happen. A response can disappear after D1 has already committed a transition. For that reason, command start and completion acknowledgements are idempotent in a narrow way:

- a start retry is accepted only when the same command is already `EXECUTING`, belongs to the same agent, and is still inside its request lifetime;
- a completion retry is accepted only when the durable receipt already stored for that command matches every submitted receipt field exactly;
- a conflicting replay is rejected rather than merged, overwritten or guessed.

The first completion still updates the command and inserts its receipt in one D1 batch. D1 executes batched statements transactionally, so the command cannot become terminal without the corresponding receipt being inserted by that batch.

These retry rules do not expand the action registry and do not create research, trading or capital authority. Their only purpose is to make an uncertain network acknowledgement safe to repeat without creating a second state transition.