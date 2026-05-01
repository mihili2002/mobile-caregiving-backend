# ml/member2_chatbot/model.py
import torch
import torch.nn as nn
import torch.nn.functional as F


class EmotionModel(nn.Module):
    """
    Matches checkpoint keys/shapes:
      conv1.weight: [16, 1, 9]
      conv2.weight: [32, 16, 9]
      conv3.weight: [64, 32, 9]
      conv4.weight: [128, 64, 9]
      fc.weight:    [num_labels, 128]

    This is a Conv1d audio model that expects input shaped:
      [B, T]  or  [B, 1, T]

    Output:
      [B, num_labels]
    """

    def __init__(self, num_labels: int = 4):
        super().__init__()

        self.conv1 = nn.Conv1d(in_channels=1, out_channels=16, kernel_size=9, padding=4)
        self.conv2 = nn.Conv1d(in_channels=16, out_channels=32, kernel_size=9, padding=4)
        self.conv3 = nn.Conv1d(in_channels=32, out_channels=64, kernel_size=9, padding=4)
        self.conv4 = nn.Conv1d(in_channels=64, out_channels=128, kernel_size=9, padding=4)

        self.pool = nn.MaxPool1d(kernel_size=2, stride=2)

        # makes output length = 1, so final feature dim = 128
        self.gap = nn.AdaptiveAvgPool1d(1)

        self.fc = nn.Linear(128, num_labels)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # accept [B, T] or [B, 1, T]
        if x.dim() == 2:
            x = x.unsqueeze(1)  # [B, 1, T]
        elif x.dim() != 3:
            raise ValueError(f"Expected input [B,T] or [B,1,T], got {tuple(x.shape)}")

        x = self.pool(F.relu(self.conv1(x)))
        x = self.pool(F.relu(self.conv2(x)))
        x = self.pool(F.relu(self.conv3(x)))
        x = self.pool(F.relu(self.conv4(x)))

        x = self.gap(x)              # [B, 128, 1]
        x = x.squeeze(-1)            # [B, 128]
        x = self.fc(x)               # [B, num_labels]
        return x
