from __future__ import annotations

import json
import inspect
import importlib
from pathlib import Path
from typing import Tuple, Optional

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import librosa


class EmotionPredictor:
    """
    Loads a PyTorch emotion model and predicts emotion from a WAV file.

    Supports:
      ✅ TorchScript (.pt saved via torch.jit.save)
      ✅ Full model object saved via torch.save(model)
      ✅ state_dict / checkpoint dict proves: torch.save({...}) or torch.save(model.state_dict())

    If it's a state_dict/checkpoint, this will try to automatically find the correct
    model class inside `ml/member2_chatbot/model.py` by inspecting nn.Module classes.
    """

    def __init__(
        self,
        model_path: Path,
        labels_path: Path,
        device: Optional[str] = None,
        sr: int = 16000,
        target_len: int = 64000,
    ):
        self.sr = sr
        self.target_len = target_len
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")

        # ---- load labels
        labels_obj = json.loads(labels_path.read_text(encoding="utf-8"))
        # supports {"labels":[...]} OR direct list [...]
        self.labels = labels_obj["labels"] if isinstance(labels_obj, dict) else labels_obj
        self.num_classes = len(self.labels)

        # ---- load model
        self.model = self._load_model(model_path)
        self.model.to(self.device)
        self.model.eval()

    # -----------------------------------------------------
    def _extract_state_dict(self, obj):
        """
        Many trainings save checkpoints like:
          {"state_dict": ..., "model_state_dict": ..., "epoch": ...}
        This extracts the actual state dict if possible.
        """
        if isinstance(obj, dict):
            for key in ("model_state_dict", "state_dict", "net", "model"):
                if key in obj and isinstance(obj[key], dict):
                    return obj[key]
        return obj if isinstance(obj, dict) else None

    def _find_model_class(self):
        """
        Tries to find the correct nn.Module class in ml/member2_chatbot/model.py
        without you hardcoding the class name.
        """
        mod = importlib.import_module("ml.member2_chatbot.model")

        # collect nn.Module subclasses
        candidates = []
        for name, cls in inspect.getmembers(mod, inspect.isclass):
            if issubclass(cls, nn.Module) and cls is not nn.Module:
                if cls.__module__ == mod.__name__:
                    candidates.append((name, cls))

        if not candidates:
            raise ImportError("No torch.nn.Module classes found in ml/member2_chatbot/model.py")

        preferred_names = [
            "EmotionModel",
            "EmotionClassifier",
            "EmotionNet",
            "AudioEmotionModel",
            "Model",
            "Net",
        ]

        name_to_cls = {n: c for n, c in candidates}
        for pname in preferred_names:
            if pname in name_to_cls:
                return pname, name_to_cls[pname]

        return candidates[0][0], candidates[0][1]

    def _infer_input_dim(self, state: dict) -> int:
        """
        Infer input_dim from a state_dict by finding the first 2D weight tensor
        (e.g., Linear weight of shape [out_features, in_features]).
        """
        for _, v in state.items():
            if torch.is_tensor(v) and v.ndim == 2:
                return int(v.shape[1])
        raise ValueError("Could not infer input_dim from state_dict (no 2D weight tensors found).")

    def _try_instantiate(self, cls, state: Optional[dict] = None):
        """
        Attempts to instantiate the model class with common argument patterns.
        If `state` is provided, can infer input_dim for models that require it.
        """
        sig = inspect.signature(cls.__init__)
        params = sig.parameters
        keys = [k for k in params.keys() if k != "self"]

        # simplest
        if not keys:
            return cls()

        inferred_input_dim = None
        if state is not None:
            try:
                inferred_input_dim = self._infer_input_dim(state)
            except Exception:
                inferred_input_dim = None

        common_kwargs = {
            # class count
            "num_labels": self.num_classes,
            "num_classes": self.num_classes,
            "n_classes": self.num_classes,
            "classes": self.num_classes,

            # audio params
            "sr": self.sr,
            "sample_rate": self.sr,
            "target_len": self.target_len,
            "input_len": self.target_len,

            # feature dims
            "input_dim": inferred_input_dim,
            "in_dim": inferred_input_dim,
            "embed_dim": inferred_input_dim,
            "feature_dim": inferred_input_dim,
        }

        usable = {k: v for k, v in common_kwargs.items() if k in params and v is not None}

        # 1) try kwargs
        try:
            return cls(**usable)
        except TypeError:
            pass

        # 2) try no args
        try:
            return cls()
        except TypeError:
            pass

        # 3) force common positional patterns
        if inferred_input_dim is not None:
            try:
                return cls(inferred_input_dim, self.num_classes)
            except TypeError:
                pass
            try:
                return cls(self.num_classes, inferred_input_dim)
            except TypeError:
                pass

        if "num_classes" in params:
            return cls(self.num_classes)

        raise TypeError(f"Could not instantiate {cls.__name__}. Required params: {list(keys)}")

    # -----------------------------------------------------
    def _load_model(self, model_path: Path):
        # 1) Try TorchScript first
        try:
            m = torch.jit.load(str(model_path), map_location=self.device)
            return m
        except Exception:
            pass

        # 2) Load normally
        obj = torch.load(str(model_path), map_location=self.device)

        # If full model saved (torch.save(model))
        if hasattr(obj, "forward"):
            return obj

        # 3) state_dict or checkpoint
        state = self._extract_state_dict(obj)
        if state is None:
            raise RuntimeError("Unsupported model file format (not TorchScript/model/state_dict).")

        # auto-discover model class
        class_name, ModelCls = self._find_model_class()

        # instantiate
        model = self._try_instantiate(ModelCls, state=state)

        # load weights (STRICT!)
        model.load_state_dict(state, strict=True)

        print(f"✅ EmotionPredictor loaded state_dict into class: {class_name}")
        return model

    # -----------------------------------------------------
    def _preprocess(self, wav_path: Path) -> torch.Tensor:
        audio, _ = librosa.load(str(wav_path), sr=self.sr, mono=True)

        # pad / trim to fixed length
        if len(audio) < self.target_len:
            pad = self.target_len - len(audio)
            audio = np.pad(audio, (0, pad), mode="constant")
        else:
            audio = audio[: self.target_len]

        x = torch.tensor(audio, dtype=torch.float32).unsqueeze(0)  # [1, T]
        return x

    # -----------------------------------------------------
    @torch.no_grad()
    def predict(self, wav_path: Path) -> Tuple[str, float]:
        x = self._preprocess(wav_path).to(self.device)

        logits = self.model(x)

        # If model returns (logits, something)
        if isinstance(logits, (tuple, list)):
            logits = logits[0]

        probs = F.softmax(logits, dim=-1).squeeze(0)

        # 🔍 DEBUG BLOCK
        topk = torch.topk(probs, k=min(4, probs.numel()))
        print("DEBUG labels:", self.labels)
        print("DEBUG probs:", probs.detach().cpu().numpy())
        print("DEBUG topk idx:", topk.indices.detach().cpu().tolist())
        print("DEBUG topk labels:", [self.labels[i] for i in topk.indices.detach().cpu().tolist()])
        print("DEBUG topk probs:", topk.values.detach().cpu().tolist())
        print("--------------------------------------------------")

        conf, idx = torch.max(probs, dim=-1)
        label = self.labels[int(idx)]
        return label, float(conf.item())
