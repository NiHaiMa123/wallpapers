# ComfyUI Qwen H3 Bilingual Director

Local custom node for this workstation. It reuses LM Studio's installed `lms.exe`
and the indexed Qwen3.6 GGUF, generates matching Chinese-review and English-H3
prompts, and unloads the model in a `finally` block before returning control to
the rest of ComfyUI.

No copy of the 21.5 GiB model and no `llama-cpp-python` installation are needed.
