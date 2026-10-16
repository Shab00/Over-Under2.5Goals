import torch
import torch.nn as nn


class HomeWinNet(nn.Module):
    """
    3-layer MLP classifier for home win prediction.
    Architecture:
      Input (218) → Linear(218, 128) → BatchNorm → ReLU → Dropout(0.3)
                  → Linear(128, 64) → BatchNorm → ReLU → Dropout(0.3)
                  → Linear(64, 1) [logits]
    Uses BCEWithLogitsLoss (combines sigmoid + BCE).
    """

    def __init__(self, input_size: int = 218, dropout: float = 0.3):
        super().__init__()
        self.fc1 = nn.Linear(input_size, 128)
        self.bn1 = nn.BatchNorm1d(128)
        self.relu1 = nn.ReLU()
        self.drop1 = nn.Dropout(dropout)

        self.fc2 = nn.Linear(128, 64)
        self.bn2 = nn.BatchNorm1d(64)
        self.relu2 = nn.ReLU()
        self.drop2 = nn.Dropout(dropout)

        self.fc3 = nn.Linear(64, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: Tensor of shape (batch_size, 218)
        Returns:
            logits: Tensor of shape (batch_size, 1)
        """
        x = self.fc1(x)
        x = self.bn1(x)
        x = self.relu1(x)
        x = self.drop1(x)

        x = self.fc2(x)
        x = self.bn2(x)
        x = self.relu2(x)
        x = self.drop2(x)

        x = self.fc3(x)
        return x
