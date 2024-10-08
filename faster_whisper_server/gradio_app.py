from collections.abc import Generator
from typing import Literal

import gradio as gr
import httpx
from httpx_sse import connect_sse
from openai import OpenAI

from faster_whisper_server.config import Config, Language, Task

TRANSCRIPTION_ENDPOINT = "/v1/audio/transcriptions"
TRANSLATION_ENDPOINT = "/v1/audio/translations"
TIMEOUT_SECONDS = 180
TIMEOUT = httpx.Timeout(timeout=TIMEOUT_SECONDS)


def create_gradio_demo(config: Config) -> gr.Blocks:
    base_url = f"http://{config.host}:{config.port}"
    http_client = httpx.Client(base_url=base_url, timeout=TIMEOUT)
    openai_client = OpenAI(base_url=f"{base_url}/v1", api_key="cant-be-empty")

    def handler(
        file_path: str,
        model: str,
        task: Task,
        temperature: float,
        stream: bool,
        language: str | None = None,
        fmt: str | None = None,
        timestamp_granularities: list[Literal["segment", "word"]] = ["segment"],
        prompt: str | None = None,
        hotwords: str | None = None,
    ) -> Generator[str, None, None]:
        if task == Task.TRANSCRIBE:
            endpoint = TRANSCRIPTION_ENDPOINT
        elif task == Task.TRANSLATE:
            endpoint = TRANSLATION_ENDPOINT

        if stream:
            previous_transcription = ""
            for transcription in streaming_audio_task(
                endpoint,
                file_path,
                model,
                temperature,
                language=language,
                fmt=fmt,
                timestamp_granularities=timestamp_granularities,
                prompt=prompt,
                hotwords=hotwords,
            ):
                previous_transcription += transcription
                yield previous_transcription
        else:
            yield audio_task(
                endpoint,
                file_path,
                model,
                temperature,
                language=language,
                fmt=fmt,
                timestamp_granularities=timestamp_granularities,
                prompt=prompt,
                hotwords=hotwords,
            )

    def audio_task(
        endpoint: str,
        file_path: str,
        model: str,
        temperature: float,
        language: str | None = None,
        fmt: str | None = None,
        timestamp_granularities: list[str] = ["segment"],
        prompt: str | None = None,
        hotwords: str | None = None,
    ) -> str:
        with open(file_path, "rb") as file:
            response = http_client.post(
                endpoint,
                files={"file": file},
                data={
                    "model": model,
                    "response_format": fmt if fmt else "text",
                    "temperature": temperature,
                    **({"language": language} if language else {}),
                    **({"prompt": prompt} if prompt else {}),
                    **({"hotwords": hotwords} if hotwords else {}),
                    **({"timestamp_granularities": timestamp_granularities} if timestamp_granularities else {}),
                },
            )

        response.raise_for_status()
        return response.text

    def streaming_audio_task(
        endpoint: str,
        file_path: str,
        model: str,
        temperature: float,
        language: str | None = None,
        fmt: str | None = None,
        timestamp_granularities: list[str] = ["segment"],
        prompt: str | None = None,
        hotwords: str | None = None,
    ) -> Generator[str, None, None]:
        with open(file_path, "rb") as file:
            kwargs = {
                "files": {"file": file},
                "data": {
                    "response_format": fmt if fmt else "text",
                    "temperature": temperature,
                    "model": model,
                    "stream": True,
                    **({"language": language} if language else {}),
                    **({"prompt": prompt} if prompt else {}),
                    **({"hotwords": hotwords} if hotwords else {}),
                    **({"timestamp_granularities": timestamp_granularities} if timestamp_granularities else {}),
                },
            }
            with connect_sse(http_client, "POST", endpoint, **kwargs) as event_source:
                for event in event_source.iter_sse():
                    yield event.data

    def update_model_dropdown() -> gr.Dropdown:
        models = openai_client.models.list().data
        model_names: list[str] = [model.id for model in models]
        assert config.whisper.model in model_names
        recommended_models = {model for model in model_names if model.startswith("Systran")}
        other_models = [model for model in model_names if model not in recommended_models]
        model_names = list(recommended_models) + other_models
        return gr.Dropdown(
            # no idea why it's complaining
            choices=model_names,  # pyright: ignore[reportArgumentType]
            label="Model",
            value=config.whisper.model,
        )

    languages_dropdown = gr.Dropdown(
        choices=[str(language) for language in Language],
        label="Language",
        value=config.default_language,
    )
    format_dropdown = gr.Dropdown(
        choices=["text", "json", "verbose_json", "srt", "vtt"],
        label="Response Format",
        value="text",
    )
    prompt_input = gr.Textbox(lines=2, placeholder="Enter your prompt here", label="Prompt")
    hotwords_list = gr.Textbox(lines=2, placeholder="Enter hotwords separated by commas", label="Hotwords")
    granularity_checkbox = gr.CheckboxGroup(
        choices=["segment", "word"],
        label="Granularity",
        value=["segment"],
    )

    model_dropdown = gr.Dropdown(
        choices=[config.whisper.model],
        label="Model",
        value=config.whisper.model,
    )
    task_dropdown = gr.Dropdown(
        choices=[task.value for task in Task],
        label="Task",
        value=Task.TRANSCRIBE,
    )
    temperature_slider = gr.Slider(minimum=0.0, maximum=1.0, step=0.1, label="Temperature", value=0.0)
    stream_checkbox = gr.Checkbox(label="Stream", value=True)
    with gr.Interface(
        title="Whisper Playground",
        description="""Consider supporting the project by starring the <a href="https://github.com/fedirz/faster-whisper-server">repository on GitHub</a>.""",  # noqa: E501
        inputs=[
            gr.Audio(type="filepath"),
            model_dropdown,
            task_dropdown,
            temperature_slider,
            stream_checkbox,
        ],
        additional_inputs=[
            languages_dropdown,
            format_dropdown,
            granularity_checkbox,
            prompt_input,
            hotwords_list,
        ],
        fn=handler,
        outputs="text",
    ) as demo:
        demo.load(update_model_dropdown, inputs=None, outputs=model_dropdown)
    return demo
