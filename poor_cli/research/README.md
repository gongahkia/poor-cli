Research code. Not part of the production agent loop.

These modules live here to keep production package files focused and to avoid cold-start imports of experimental dependencies. Any new research module must be loaded through `poor_cli.research_loader`, must have a config flag under `research.<name>.enabled`, and must default off.

Local cold-start check on 2026-04-12, 10 subprocess runs of `python3 -c "import time; s=time.time(); import poor_cli; print(time.time()-s)"`: before mean `0.000081s`, after mean `0.000529s`, delta `+0.000448s`.
