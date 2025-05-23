import os
import sys
import threading
import time

import gradio as gr


def stop_after_delay(demo, delay_seconds):
    time.sleep(delay_seconds)
    os._exit(0)


def greet(name, intensity):
    result = "Hello, " + name + "!" * int(intensity)
    threading.Thread(target=stop_after_delay,
                     args=(demo, 2), daemon=True).start()
    return result


demo = gr.Interface(
    fn=greet,
    inputs=["text", "slider"],
    outputs=["text"],
)

if __name__ == "__main__":
    demo.launch(ssl_verify=False, server_name="0.0.0.0")
