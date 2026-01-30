
import os
import json
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from scipy.optimize import linear_sum_assignment
import warnings
from .filter import KalmanFilter

warnings.filterwarnings('ignore')


@dataclass
class Detection:
    bbox: np.ndarray  # [x, y, w, h] format 
    confidence: float
    class_id: int
    filename: str
    frame_idx: int
    appearance_feat: Optional[np.ndarray] = None
    
    def get_area(self) -> float:
        x, y, w, h = self.bbox
        return float(w * h)
    
    def get_center(self) -> np.ndarray:
        x, y, w, h = self.bbox
        return np.array([x + w / 2, y + h / 2], dtype=np.float32)
    
    def get_width_height(self) -> Tuple[float, float]:
        x, y, w, h = self.bbox
        return float(w), float(h)

@dataclass
class Track:
    """추적 경로(Track) 정보"""
    track_id: int
    detections: List[Detection] = field(default_factory=list)
    last_frame_idx: int = -1
    time_since_update: int = 0
    is_confirmed: bool = False
    kalman_filter: Optional[KalmanFilter] = None
    
    def __post_init__(self):
        self.kalman_filter = KalmanFilter()
    
    def add_detection(self, detection: Detection):
        self.detections.append(detection)
        self.last_frame_idx = detection.frame_idx
        self.time_since_update = 0
        
        # Kalman filter 업데이트
        center = detection.get_center()
        if len(self.detections) == 1:
            self.kalman_filter.initialize(center)
        else:
            self.kalman_filter.update(center)
    
    
    def increment_age(self):
        self.time_since_update += 1
    
    def get_latest_detection(self) -> Optional[Detection]:
        return self.detections[-1] if self.detections else None
    
    def get_best_detection(self, metric="confidence") -> Detection:
        if metric == "area":
            return max(self.detections, key=lambda d: d.get_area())
        elif metric == "confidence":
            return max(self.detections, key=lambda d: d.confidence)
        else:
            return self.detections[-1]
    
    def get_velocity(self) -> Optional[np.ndarray]:
        """현재 추적의 속도 반환"""
        if self.kalman_filter.x is not None:
            return self.kalman_filter.x[2:4]
        return None
    
    def predict_next_bbox(self, dt: float = 1.0) -> Optional[np.ndarray]:
        """다음 프레임의 예상 bbox 반환"""
        if len(self.detections) < 2:
            return None
        
        latest_det = self.get_latest_detection()
        if latest_det is None:
            return None
        
        predicted_center = self.kalman_filter.predict()
        if predicted_center is None:
            return predicted_center
        
        w, h = latest_det.get_width_height()
        x1 = predicted_center[0] - w / 2
        y1 = predicted_center[1] - h / 2
        return np.array([x1, y1, x1 + w, y1 + h], dtype=np.float32)


class ByteTrackAdvanced:
    
    def __init__(
        self,
        data_dir: str,
        iou_thresh_high: float = 0.2,
        iou_thresh_low: float = 0.1,
        confidence_thresh: float = 0.5,
        max_age: int = 30,
        use_appearance: bool = False,
    ):
        self.data_dir = Path(data_dir)
        self.iou_thresh_high = iou_thresh_high
        self.iou_thresh_low = iou_thresh_low
        self.confidence_thresh = confidence_thresh
        self.max_age = max_age
        self.use_appearance = use_appearance
        self.tracks: Dict[int, Track] = {}
        self.next_track_id = 0
    
    @staticmethod
    def iou(box1: np.ndarray, box2: np.ndarray) -> float:
        x1, y1, w, h = box1
        x2, y2, w2, h2 = box2
        
        inter_xmin = max(x1, x2)
        inter_ymin = max(y1, y2)
        inter_xmax = min(x1 + w, x2 + w2)
        inter_ymax = min(y1 + h, y2 + h2)
        
        if inter_xmax <= inter_xmin or inter_ymax <= inter_ymin:
            return 0.0
        
        inter_area = (inter_xmax - inter_xmin) * (inter_ymax - inter_ymin)
        area1 = w * h
        area2 = w2 * h2
        union_area = area1 + area2 - inter_area
        
        return float(inter_area / union_area) if union_area > 0 else 0.0
    
    #낮을수록 유사도가 높음
    def _motion_distance(
        self, detection: Detection, track: Track
    ) -> float:

        
        predicted_bbox = track.predict_next_bbox()
        if predicted_bbox is None:
            return float('inf')
        
        # Prediction error (center distance)
        pred_center = (predicted_bbox[:2] + predicted_bbox[2:]) / 2
        curr_center = detection.get_center()
        distance = np.linalg.norm(pred_center - curr_center)
        
        return distance
    
    def _appearance_distance(
        self, detection: Detection, track: Track
    ) -> float:
        """Appearance-based distance"""
        if not self.use_appearance or detection.appearance_feat is None:
            return 0.0
        
        latest_det = track.get_latest_detection()
        if latest_det is None or latest_det.appearance_feat is None:
            return 0.0
        
        # Cosine similarity
        feat1 = detection.appearance_feat / (np.linalg.norm(detection.appearance_feat) + 1e-6)
        feat2 = latest_det.appearance_feat / (np.linalg.norm(latest_det.appearance_feat) + 1e-6)
        similarity = np.dot(feat1, feat2)
        
        return 1.0 - similarity  # Distance
    
    def _compute_cost_matrix(
        self,
        detections: List[Detection],
        tracks: List[Track],
        iou_thresh: float,
    ) -> np.ndarray:

        n_det = len(detections)
        n_track = len(tracks)
        
        if n_det == 0 or n_track == 0:
            return np.empty((n_det, n_track), dtype=np.float32)
        
        cost_matrix = np.zeros((n_det, n_track), dtype=np.float32)
        
        for d_idx, detection in enumerate(detections):
            for t_idx, track in enumerate(tracks):
                latest_det = track.get_latest_detection()
                if latest_det is None:
                    cost_matrix[d_idx, t_idx] = float('inf')
                    continue
                
                # IoU 기반 cost
                iou_val = self.iou(detection.bbox, latest_det.bbox)
                if iou_val < iou_thresh:
                    cost_matrix[d_idx, t_idx] = float('inf')
                    continue
                
                iou_cost = 1.0 - iou_val  # IoU 역수
                
                # Motion cost
                motion_cost = self._motion_distance(detection, track)
                motion_cost = motion_cost / 100.0 if motion_cost != float('inf') else 1.0
                
                # Appearance cost
                app_cost = self._appearance_distance(detection, track)
                
                # 가중 합
                cost = 0.5 * iou_cost + 0.3 * motion_cost + 0.2 * app_cost
                cost_matrix[d_idx, t_idx] = cost
        
        return cost_matrix
    
    def _hungarian_matching(self, cost_matrix: np.ndarray, max_cost: float = 0.7):
        if cost_matrix.size == 0:
            return [], list(range(cost_matrix.shape[0])), list(range(cost_matrix.shape[1]))

        cm = cost_matrix.copy()
        cm[~np.isfinite(cm)] = 1e6  # inf, nan 제거

        det_indices, track_indices = linear_sum_assignment(cm)

        matches = []
        matched_det = set()
        matched_track = set()

        for d_idx, t_idx in zip(det_indices, track_indices):
            if cost_matrix[d_idx, t_idx] < max_cost:
                matches.append((d_idx, t_idx))
                matched_det.add(d_idx)
                matched_track.add(t_idx)

        unmatched_det = [i for i in range(cost_matrix.shape[0]) if i not in matched_det]
        unmatched_track = [i for i in range(cost_matrix.shape[1]) if i not in matched_track]
        return matches, unmatched_det, unmatched_track
    
    def _load_frame_detections(
        self, frame_filenames: List[str]
    ) -> List[List[Detection]]:
        frame_detections: List[List[Detection]] = []
        
        for frame_idx, filename in enumerate(frame_filenames):
            json_path = (self.data_dir / filename).with_suffix(".json")
            
            if not json_path.exists():
                frame_detections.append([])
                continue
            
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    anno = json.load(f)["annotations"]
            except Exception as e:
                print(f"Error loading {json_path}: {e}")
                frame_detections.append([])
                continue
            
            detections = []
            for ann in anno:

                bbox = ann.get("bbox", [])
                
                bbox_tlbr = np.array(bbox, dtype=np.float32)

                confidence = float(ann.get("confidence", 1.0))
                class_id = int(ann.get("class_id", 0))
                
                detection = Detection(
                    bbox=bbox_tlbr,
                    confidence=confidence,
                    class_id=class_id,
                    filename=filename,
                    frame_idx=frame_idx,
                )
                detections.append(detection)
            
            frame_detections.append(detections)
        
        return frame_detections
    
    def update(self, frame_detections: List[List[Detection]]):
        """ByteTrack 업데이트 (Hungarian Algorithm 사용)"""

        for frame_idx, detections in enumerate(frame_detections):
            high_conf_dets = [d for d in detections if d.confidence >= self.confidence_thresh]
            low_conf_dets = [d for d in detections if d.confidence < self.confidence_thresh]
            active_tracks = [
                t for t in self.tracks.values() if t.time_since_update < self.max_age
            ]
            
            # High confidence 매칭
            cost_high = self._compute_cost_matrix(
                high_conf_dets, active_tracks, self.iou_thresh_high
            )
            matches_high, unmatch_high_dets, unmatch_high_tracks = (
                self._hungarian_matching(cost_high, max_cost=0.5)
            )
            
            for d_idx, t_idx in matches_high:
                active_tracks[t_idx].add_detection(high_conf_dets[d_idx])
                active_tracks[t_idx].is_confirmed = True
            
            for d_idx in unmatch_high_dets:
                new_track = Track(track_id=self.next_track_id)
                new_track.add_detection(high_conf_dets[d_idx])
                new_track.is_confirmed = True
                self.tracks[self.next_track_id] = new_track
                self.next_track_id += 1
            
            # Low confidence 매칭
            unmatched_active_tracks = [active_tracks[i] for i in unmatch_high_tracks]
            confirmed_tracks = [t for t in unmatched_active_tracks if t.is_confirmed]
            
            cost_low = self._compute_cost_matrix(
                low_conf_dets, confirmed_tracks, self.iou_thresh_low
            )
            matches_low, _, _ = self._hungarian_matching(cost_low, max_cost=0.7)
            
            for d_idx, t_idx in matches_low:
                confirmed_tracks[t_idx].add_detection(low_conf_dets[d_idx])

            for track_id, track in list(self.tracks.items()):
                if track.time_since_update == 0:
                    continue
                
                track.increment_age()
                if track.time_since_update > self.max_age:
                    del self.tracks[track_id]
    
    
    def select_best_filenames(self, frame_filenames: List[str]) -> List[str]:
        frame_detections = self._load_frame_detections(frame_filenames)

        self.update(frame_detections)

        
        selected = []
        for track_id, track in sorted(self.tracks.items()):
            if len(track.detections) == 0:
                continue
            best_det = track.get_best_detection(metric="confidence")
            selected.append(best_det.filename)
        
        unique_files = list(dict.fromkeys(selected))
        return unique_files
    
    def get_track_summary(self) -> Dict[int, Dict]:
        summary = {}
        for track_id, track in self.tracks.items():
            if len(track.detections) == 0:
                continue
            
            best_det = track.get_best_detection(metric="confidence")
            velocity = track.get_velocity()
            
            summary[track_id] = {
                "track_id": track_id,
                "num_detections": len(track.detections),
                "confidence": float(best_det.confidence),
                "best_bbox": best_det.bbox.tolist(),
                "best_filename": best_det.filename,
                "first_frame": track.detections[0].frame_idx,
                "last_frame": track.detections[-1].frame_idx,
                "duration": track.detections[-1].frame_idx - track.detections[0].frame_idx + 1,
                "is_confirmed": track.is_confirmed,
                "velocity": velocity.tolist() if velocity is not None else None,
            }
        
        return summary


def main():
    print("=" * 80)
    print("ByteTrack Advanced Instance Separator")
    print("=" * 80)
    
    selector = ByteTrackAdvanced(
        data_dir="../samples",
        iou_thresh_high=0.3,
        iou_thresh_low=0.1,
        confidence_thresh=0.5,
        max_age=30,

    )
    
    frame_files = sorted([p.name for p in selector.data_dir.glob("*.jpg")])[:10]
    if not frame_files:
        print(f"No JPG files found in {selector.data_dir}")
        return
    
    print(f"\nProcessing {len(frame_files)} frames...")
    selected_files = selector.select_best_filenames(frame_files)
    
    print(f"\nSelected {len(selected_files)} unique instances:")
    for f in selected_files:
        print(f"  ✓ {f}")
    
    print(f"\n" + "=" * 80)
    print(f"Track Details:")
    print("=" * 80)
    summary = selector.get_track_summary()
    for track_id, info in sorted(summary.items()):
        print(f"\n[Track {track_id:02d}]")
        print(f"  Detections:  {info['num_detections']}")
        print(f"  Duration:    {info['duration']} frames")
        print(f"  Confidence:  {info['confidence']:.3f}")
        print(f"  Best Frame:  {info['best_filename']}")
        print(f"  BBox:        {[f'{x:.1f}' for x in info['best_bbox']]}")
        print(f"  Confirmed:   {'Yes' if info['is_confirmed'] else 'No'}")
        if info['velocity'] is not None:
            print(f"  Velocity:    [{info['velocity'][0]:.2f}, {info['velocity'][1]:.2f}]")


if __name__ == "__main__":
    main()