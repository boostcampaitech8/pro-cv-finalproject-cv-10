import os
import json
import numpy as np
from pathlib import Path
from typing import Dict, List


class InstanceSelector:
    def __init__(self, data_dir: str, iou_thresh: float = 0.3):
        self.data_dir = Path(data_dir)
        self.iou_thresh = iou_thresh
        self.last_chosen_files = []  # 최근에 선택된 파일 목록 저장용 변수

    def bbox_to_tlbr(self, bbox: List[float]) -> np.ndarray:
        x, y, w, h = bbox
        return np.array([x, y, x + w, y + h], dtype=np.float32)

    def calculate_quality_score(self, bbox: List[float]) -> float:
        # "가장 잘 보이는" 간단 기준: bbox area 최대
        x, y, w, h = bbox
        return float(w * h)

    def iou(self, box1_tlbr: np.ndarray, box2_tlbr: np.ndarray) -> float:
        x1_min, y1_min, x1_max, y1_max = box1_tlbr
        x2_min, y2_min, x2_max, y2_max = box2_tlbr

        inter_xmin = max(x1_min, x2_min)
        inter_ymin = max(y1_min, y2_min)
        inter_xmax = min(x1_max, x2_max)
        inter_ymax = min(y1_max, y2_max)

        if inter_xmax <= inter_xmin or inter_ymax <= inter_ymin:
            return 0.0

        inter_area = (inter_xmax - inter_xmin) * (inter_ymax - inter_ymin)
        area1 = (x1_max - x1_min) * (y1_max - y1_min)
        area2 = (x2_max - x2_min) * (y2_max - y2_min)
        union_area = area1 + area2 - inter_area
        return float(inter_area / union_area) if union_area > 0 else 0.0

    def _load_frame_detections(self, frame_filenames: List[str]) -> List[List[Dict]]:
        frame_detections: List[List[Dict]] = []

        for filename in frame_filenames:
            json_path = (self.data_dir / filename).with_suffix(".json") 
            if not json_path.exists():
                frame_detections.append([])
                continue

            with open(json_path, "r", encoding="utf-8") as f:
                anno = json.load(f)

            detections = []
            for ann in anno.get("annotations", []):
                detections.append(
                    {
                        "filename": filename,              
                        "bbox": ann["bbox"],
                        "class": ann.get("class", "0"),
                        "area": ann.get("area", 0),
                        "full_annotation": ann,
                    }
                )
            frame_detections.append(detections)

        return frame_detections

    def match_instances_across_frames(
        self, frame_detections: List[List[Dict]]
    ) -> Dict[int, List[Dict]]:
        instance_tracks: Dict[int, List[Dict]] = {}
        next_instance_id = 0

        for frame_idx, detections in enumerate(frame_detections):
            if frame_idx == 0:
                for det in detections:
                    instance_tracks[next_instance_id] = [det]
                    next_instance_id += 1
                continue

            matched_tracks = set()

            for det in detections:
                best_track_id = None
                best_iou = self.iou_thresh

                curr_bbox = self.bbox_to_tlbr(det["bbox"])

                for track_id, track_dets in instance_tracks.items():
                    if track_id in matched_tracks:
                        continue

                    last_det = track_dets[-1]
                    last_bbox = self.bbox_to_tlbr(last_det["bbox"])
                    curr_iou = self.iou(last_bbox, curr_bbox)

                    if curr_iou > best_iou:
                        best_iou = curr_iou
                        best_track_id = track_id

                if best_track_id is not None:
                    instance_tracks[best_track_id].append(det)
                    matched_tracks.add(best_track_id)
                else:
                    instance_tracks[next_instance_id] = [det]
                    next_instance_id += 1

        return instance_tracks

    def select_best_filenames(self, frame_filenames: List[str]) -> List[str]:
        """
        입력: 연속된 10장 jpg 파일명 리스트 (store 내부에 jpg/json 동명 존재)
        출력: 각 instance에서 '가장 잘 보이는' 프레임의 jpg 파일명 리스트(중복 제거, 원본 파일명 그대로)
        """
        frame_detections = self._load_frame_detections(frame_filenames)
        instance_tracks = self.match_instances_across_frames(frame_detections)

        selected: List[str] = []
        for instance_id, track_dets in instance_tracks.items():
            if not track_dets:
                continue

            best_det = max(track_dets, key=lambda d: self.calculate_quality_score(d["bbox"]))
            selected.append(best_det["filename"])

        # 중복 제거(순서 유지)
        uniq = list(dict.fromkeys(selected))
        # 최근에 선택된 파일은 제외
        for filename in uniq:
            if filename in self.last_chosen_files:
                uniq.remove(filename)
        self.last_chosen_files = uniq  # 최근에 선택된 파일 목록 저장
        return uniq


def main():
    selector = InstanceSelector(data_dir="./store", iou_thresh=0.2)

    frame_files = sorted([p.name for p in selector.data_dir.glob("*.jpg")])[:10]
    if not frame_files:
        print(f"No JPG files found in {selector.data_dir}")
        return

    selected_files = selector.select_best_filenames(frame_files)
    print("Selected files:")
    for f in selected_files:
        print(f)


if __name__ == "__main__":
    main()
