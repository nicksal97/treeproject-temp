"""
Geometry and path processing utilities
"""
from collections import deque
from math import sqrt, atan2, degrees
import numpy as np
from scipy.interpolate import splprep, splev
from shapely.geometry import Polygon


def polygon_area(vertices):
    """Calculate the area of a polygon given its vertices."""
    polygon = Polygon(vertices)
    return polygon.area


def distance(p1, p2):
    """Calculate Euclidean distance between two points."""
    return sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)


def are_connected_or_close(seg1, seg2, threshold):
    """Check if two segments are connected or close based on the threshold."""
    return (
        distance(seg1[0], seg2[0]) < threshold or
        distance(seg1[0], seg2[1]) < threshold or
        distance(seg1[1], seg2[0]) < threshold or
        distance(seg1[1], seg2[1]) < threshold
    )


def find_groups(segments, threshold):
    """Group segments based on connectivity or proximity."""
    groups = []
    visited = set()
    
    for segment in segments:
        if segment in visited:
            continue
        
        group = [segment]
        visited.add(segment)
        queue = deque([segment])
        
        while queue:
            current_segment = queue.popleft()
            for seg in segments:
                if seg not in visited and are_connected_or_close(current_segment, seg, threshold):
                    visited.add(seg)
                    group.append(seg)
                    queue.append(seg)
        
        groups.append(group)
    
    return groups


def collect_points(group):
    """Collect all points from a group of segments."""
    points = []
    for seg in group:
        points.extend(seg)
    return points


def sort_points(points):
    """Sort points based on their x-coordinates (and y-coordinates if needed)."""
    return sorted(points, key=lambda point: (point[0], point[1]))


def predict_direction(p1, p2):
    """Calculate the angle of the line formed by two points."""
    return degrees(atan2(p2[1] - p1[1], p2[0] - p1[0]))


def filter_zigzag(points, tolerance=50):
    """Filter out points that deviate significantly from the predicted direction."""
    if len(points) < 3:
        return points
    
    filtered_points = [points[0]]
    
    for i in range(1, len(points) - 1):
        prev_point = filtered_points[-1]
        current_point = points[i]
        next_point = points[i + 1]
        
        direction_prev = predict_direction(prev_point, current_point)
        direction_next = predict_direction(current_point, next_point)
        
        if abs(direction_next - direction_prev) <= tolerance:
            filtered_points.append(current_point)
    
    filtered_points.append(points[-1])
    return filtered_points


def smooth_path(points, smoothing_factor=0):
    """Smooth the path using cubic splines."""
    if len(points) < 5:
        return points
    
    # Remove duplicate points
    points = list(dict.fromkeys(points))
    
    if len(points) < 2:
        return points
    
    x = [p[0] for p in points]
    y = [p[1] for p in points]
    
    k = min(3, len(points) - 1)
    
    try:
        tck, u = splprep([x, y], s=smoothing_factor, k=k)
        u_fine = np.linspace(0, 1, len(points) * 10)
        x_fine, y_fine = splev(u_fine, tck)
        smoothed_points = list(zip(np.int32(x_fine), np.int32(y_fine)))
        return smoothed_points
    except Exception as e:
        print(f"Error in smoothing path: {e}")
        return points

