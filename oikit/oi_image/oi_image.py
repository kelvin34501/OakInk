import json
import os
import pickle

import imageio
import numpy as np
import trimesh

from .utils import load_object, load_object_by_id, persp_project, suppress_trimesh_logging


def decode_seq_cat(seq_cat):
    field_list = seq_cat.split("_")
    obj_id = field_list[0]
    action_id = field_list[1]
    if action_id == "0004":
        subject_id = tuple(field_list[2:4])
    else:
        subject_id = (field_list[2],)
    return obj_id, action_id, subject_id


class OakInkImage:

    def __init__(self, data_split="all", mode_split="default") -> None:
        self._name = "OakInkImage"
        self._data_split = data_split
        self._mode_split = mode_split
        assert 'OAKINK_DIR' in os.environ, "environment variable 'OAKINK_DIR' is not set"

        self._data_dir = os.environ['OAKINK_DIR']
        self.info_list = json.load(open(os.path.join(self._data_dir, "image", "anno", "seq_all.json")))
        self.info_str_list = []
        for info in self.info_list:
            info_str = "__".join([str(x) for x in info])
            info_str = info_str.replace("/", "__")
            self.info_str_list.append(info_str)

        # load obj
        suppress_trimesh_logging()

        self.obj_mapping = {}
        obj_root = os.path.join(self._data_dir, "image", "obj")
        all_obj_fn = sorted(os.listdir(obj_root))
        for obj_fn in all_obj_fn:
            obj_id = os.path.splitext(obj_fn)[0]
            obj_model = load_object(obj_root, obj_fn)
            self.obj_mapping[obj_id] = obj_model

        self.framedata_color_name = [
            "north_east_color",
            "south_east_color",
            "north_west_color",
            "south_west_color",
        ]

        self._image_size = (848, 480)  # (W, H)
        self._hand_side = "right"

        # seq status
        with open(os.path.join(self._data_dir, "image", "anno", "seq_status.json"), "r") as f:
            self.seq_status = json.load(f)

    def __len__(self):
        return len(self.info_list)

    def get_image_path(self, idx):
        info = self.info_list[idx]
        # compute image path
        offset = os.path.join(info[0], f"{self.framedata_color_name[info[3]]}_{info[2]}.png")
        image_path = os.path.join(self._data_dir, "image", "stream_release_v2", offset)
        return image_path

    def get_image(self, idx):
        path = self.get_image_path(idx)
        image = np.array(imageio.imread(path, pilmode="RGB"), dtype=np.uint8)
        return image

    def get_cam_intr(self, idx):
        cam_path = os.path.join(self._data_dir, "image", "anno", "cam_intr", f"{self.info_str_list[idx]}.pkl")
        with open(cam_path, "rb") as f:
            cam_intr = pickle.load(f)
        return cam_intr

    def get_joints_3d(self, idx):
        joints_path = os.path.join(self._data_dir, "image", "anno", "hand_j", f"{self.info_str_list[idx]}.pkl")
        with open(joints_path, "rb") as f:
            joints_3d = pickle.load(f)
        return joints_3d

    def get_verts_3d(self, idx):
        verts_path = os.path.join(self._data_dir, "image", "anno", "hand_v", f"{self.info_str_list[idx]}.pkl")
        with open(verts_path, "rb") as f:
            verts_3d = pickle.load(f)
        return verts_3d

    def get_joints_2d(self, idx):
        cam_intr = self.get_cam_intr(idx)
        joints_3d = self.get_joints_3d(idx)
        return persp_project(joints_3d, cam_intr)

    def get_verts_2d(self, idx):
        cam_intr = self.get_cam_intr(idx)
        verts_3d = self.get_verts_3d(idx)
        return persp_project(verts_3d, cam_intr)

    def get_mano_pose(self, idx):
        pass

    def get_mano_shape(self, idx):
        pass

    def get_obj_idx(self, idx):
        info = self.info_list[idx][0]
        seq_cat, _ = info.split("/")
        obj_id, _, _ = decode_seq_cat(seq_cat)
        return obj_id

    def get_obj_faces(self, idx):
        obj_id = self.get_obj_idx(idx)
        return np.asarray(self.obj_mapping[obj_id].faces).astype(np.int32)

    def get_obj_transf(self, idx):
        obj_transf_path = os.path.join(self._data_dir, "image", "anno", "obj_transf", f"{self.info_str_list[idx]}.pkl")
        with open(obj_transf_path, "rb") as f:
            obj_transf = pickle.load(f)
        return obj_transf.astype(np.float32)

    def get_obj_verts_3d(self, idx):
        obj_verts = self.get_obj_verts_can(idx)
        obj_transf = self.get_obj_transf(idx)
        obj_rot = obj_transf[:3, :3]
        obj_tsl = obj_transf[:3, 3]
        obj_verts_transf = (obj_rot @ obj_verts.transpose(1, 0)).transpose(1, 0) + obj_tsl
        return obj_verts_transf

    def get_obj_verts_2d(self, idx):
        obj_verts_3d = self.get_obj_verts_3d(idx)
        cam_intr = self.get_cam_intr(idx)
        return persp_project(obj_verts_3d, cam_intr)

    def get_obj_verts_can(self, idx):
        obj_id = self.get_obj_idx(idx)
        obj_verts = np.asarray(self.obj_mapping[obj_id].vertices).astype(np.float32)
        return obj_verts

    def get_corners_3d(self, idx):
        obj_corners = self.get_corners_can(idx)
        obj_transf = self.get_obj_transf(idx)
        obj_rot = obj_transf[:3, :3]
        obj_tsl = obj_transf[:3, 3]
        obj_corners_transf = (obj_rot @ obj_corners.transpose(1, 0)).transpose(1, 0) + obj_tsl
        return obj_corners_transf

    def get_corners_2d(self, idx):
        obj_corners = self.get_corners_3d(idx)
        cam_intr = self.get_cam_intr(idx)
        return persp_project(obj_corners, cam_intr)

    def get_corners_can(self, idx):
        obj_id = self.get_obj_idx(idx)
        obj_mesh = self.obj_mapping[obj_id]
        obj_corners = trimesh.bounds.corners(obj_mesh.bounds)
        return obj_corners

    def get_sample_status(self, idx):
        info = self.info_list[idx][0]
        status = self.seq_status[info]
        return status


class OakInkImageSequence(OakInkImage):

    def __init__(self, seq_id, view_id) -> None:

        self.framedata_color_name = [
            "north_east_color",
            "south_east_color",
            "north_west_color",
            "south_west_color",
        ]
        view_name = self.framedata_color_name[view_id]
        self._name = f"OakInkImage_{seq_id}_{view_name}"

        assert 'OAKINK_DIR' in os.environ, "environment variable 'OAKINK_DIR' is not set"
        self._data_dir = os.environ['OAKINK_DIR']
        info_list_all = json.load(open(os.path.join(self._data_dir, "image", "anno", "seq_all.json")))

        seq_cat, seq_timestamp = seq_id.split("/")
        self.info_list = [info for info in info_list_all if (info[0] == seq_id and info[3] == view_id)]

        # deal with two hand cases.
        self.info_list.sort(key=lambda x: x[1] * 1000 + x[2])

        self.info_str_list = []
        for info in self.info_list:
            info_str = "__".join([str(x) for x in info])
            info_str = info_str.replace("/", "__")
            self.info_str_list.append(info_str)

        self.obj_id, self.intent_id, self.subject_id = decode_seq_cat(seq_cat)
        # load obj
        self.obj_mapping = {}
        suppress_trimesh_logging()
        obj_root = os.path.join(self._data_dir, "image", "obj")
        self.obj_model = load_object_by_id(self.obj_id, obj_root)
        self.obj_mapping[self.obj_id] = self.obj_model

        self._image_size = (848, 480)  # (W, H)
        self._hand_side = "right"
