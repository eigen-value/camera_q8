"""Style transfer con modelli ONNX locali, download automatico e fallback GPU/CPU."""

import logging
import urllib.request
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

log = logging.getLogger("style_transfer")

MODEL_DIR = Path(__file__).resolve().parent / "models"
MODEL_DIR.mkdir(exist_ok=True)

MODELS = {
    # "hayao": (
    #     "AnimeGANv2_Hayao.onnx",
    #     "https://raw.githubusercontent.com/TachibanaYoshino/AnimeGANv2/master/pb_and_onnx_model/AnimeGANv2_Hayao.onnx",
    # ),

    # "paprika": (
    #     "AnimeGANv2_Paprika.onnx",
    #     "https://raw.githubusercontent.com/TachibanaYoshino/AnimeGANv2/master/pb_and_onnx_model/AnimeGANv2_Paprika.onnx",
    # ),

    "shinkai": (
        "Shinkai_53.onnx",
        "https://raw.githubusercontent.com/xuanhao44/AnimeGANv2/main/pb_and_onnx_model/Shinkai_53.onnx",
    ),

    # "anime_face": (
    #     "AnimeGANv3_JP_face_v1.0.onnx",
    #     "https://raw.githubusercontent.com/TachibanaYoshino/AnimeGANv3/master/pb_and_onnx_model/AnimeGANv3_JP_face_v1.0.onnx",
    # ),
    #
    # "portrait_sketch": (
    #     "AnimeGANv3_PortraitSketch_25.onnx",
    #     "https://raw.githubusercontent.com/TachibanaYoshino/AnimeGANv3/master/pb_and_onnx_model/AnimeGANv3_PortraitSketch_25.onnx",
    # ),

    "candy": (
        "candy.onnx",
        "https://raw.githubusercontent.com/yakhyo/fast-neural-style-transfer/master/weights/candy.onnx",
    ),
    "mosaic": (
        "mosaic.onnx",
        "https://raw.githubusercontent.com/yakhyo/fast-neural-style-transfer/master/weights/mosaic.onnx",
    ),

    "rain_princess": (
        "rain-princess.onnx",
        "https://raw.githubusercontent.com/yakhyo/fast-neural-style-transfer/master/weights/rain-princess.onnx",
    ),

    "udnie": (
        "udnie.onnx",
        "https://raw.githubusercontent.com/yakhyo/fast-neural-style-transfer/master/weights/udnie.onnx",
    ),
}


def _download_model(name: str, url: str) -> Path:
    dest = MODEL_DIR / name
    if dest.exists():
        return dest
    log.info("Download modello %s ...", name)
    tmp = dest.with_suffix(".tmp")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as resp, open(tmp, "wb") as f:
        f.write(resp.read())
    tmp.rename(dest)
    log.info("Modello %s scaricato (%.1f MB)", name, dest.stat().st_size / 1e6)
    return dest


def ensure_models():
    for style, (fname, url) in MODELS.items():
        _download_model(fname, url)


class StyleTransfer:
    def __init__(self, input_size: int = 512):
        self.input_size = input_size
        self._sessions: dict[str, ort.InferenceSession] = {}
        self._input_nhwc: dict[str, bool] = {}  # True se il modello usa NHWC

    def _get_session(self, style: str) -> ort.InferenceSession:
        if style not in self._sessions:
            fname, _ = MODELS[style]
            path = MODEL_DIR / fname
            providers = self._select_providers()
            session = ort.InferenceSession(str(path), providers=providers)
            self._sessions[style] = session

            # Rileva il formato di input dalla shape del modello
            input_shape = session.get_inputs()[0].shape
            # Se l'ultima dimensione è 3 (canali), è NHWC
            self._input_nhwc[style] = len(input_shape) == 4 and input_shape[3] == 3
            log.info(
                "Sessione ONNX per %s su %s (input %s)",
                style,
                session.get_providers(),
                "NHWC" if self._input_nhwc[style] else "NCHW",
            )
        return self._sessions[style]

    @staticmethod
    def _select_providers():
        available = ort.get_available_providers()
        if "QNNExecutionProvider" in available:
            return ["QNNExecutionProvider", "CPUExecutionProvider"]
        return ["CPUExecutionProvider"]

    def apply(self, frame: np.ndarray, style: str) -> np.ndarray:
        """frame: HWC uint8 RGB. Restituisce HWC uint8 RGB stilizzato."""
        session = self._get_session(style)
        h, w = frame.shape[:2]

        inp = cv2.resize(frame, (self.input_size, self.input_size))
        inp = inp.astype(np.float32) / 127.5 - 1.0

        if self._input_nhwc[style]:
            # AnimeGANv2: NHWC -> (1, H, W, 3)
            inp = inp[None, ...]
        else:
            # Fast NST: NCHW -> (1, 3, H, W)
            inp = np.transpose(inp, (2, 0, 1))[None, ...]

        input_name = session.get_inputs()[0].name
        output = session.run(None, {input_name: inp})[0]

        # Postprocessing
        if self._input_nhwc[style]:
            out = output[0]  # già HWC
        else:
            out = output[0].transpose(1, 2, 0)  # NCHW -> HWC

        out = ((out + 1.0) * 127.5).clip(0, 255).astype(np.uint8)
        out = cv2.resize(out, (w, h))
        return out