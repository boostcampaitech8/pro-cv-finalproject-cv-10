import numpy as np

class KalmanFilter:
    """Kalman Filter - Motion 예측용"""
    
    def __init__(self, dt: float = 1.0):
        self.dt = dt
        self.x = None  # State: [x, y, vx, vy]
        self.P = None  # Covariance matrix
        self.Q = np.eye(4) * 0.1  # Process noise
        self.R = np.eye(2) * 10.0  # Measurement noise
    
    def initialize(self, center: np.ndarray):
        """중심 위치로 초기화"""
        self.x = np.array([center[0], center[1], 0.0, 0.0], dtype=np.float32)
        self.P = np.eye(4) * 100.0
    
    def predict(self) -> np.ndarray:
        """다음 위치 예측"""
        if self.x is None:
            return None
        
        # State transition
        F = np.array([
            [1, 0, self.dt, 0],
            [0, 1, 0, self.dt],
            [0, 0, 1, 0],
            [0, 0, 0, 1]
        ], dtype=np.float32)
        
        self.x = F @ self.x
        self.P = F @ self.P @ F.T + self.Q
        
        return self.x[:2]  # Return predicted center
    
    def update(self, center: np.ndarray):
        """관측값으로 업데이트"""
        if self.x is None:
            self.initialize(center)
            return
        
        # Measurement update
        z = center
        H = np.array([[1, 0, 0, 0], [0, 1, 0, 0]], dtype=np.float32)
        
        y = z - H @ self.x  # Residual
        S = H @ self.P @ H.T + self.R
        K = self.P @ H.T @ np.linalg.inv(S)
        
        self.x = self.x + K @ y
        self.P = (np.eye(4) - K @ H) @ self.P
