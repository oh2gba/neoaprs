// The pictures of the (i) notes by name: each is a component that draws one small picture (HelpFrame), so that InfoTip can show the one a note asks for.
import type { Component } from "vue";
import BeaconPicture from "@/help/BeaconPicture.vue";
import BulletinPicture from "@/help/BulletinPicture.vue";
import ObjectPicture from "@/help/ObjectPicture.vue";
import PathPicture from "@/help/PathPicture.vue";
import RangePicture from "@/help/RangePicture.vue";
import RequestPicture from "@/help/RequestPicture.vue";
import StatusPicture from "@/help/StatusPicture.vue";
import type { PictureName } from "@/help/names";

export const PICTURES: Record<PictureName, Component> = {
  object: ObjectPicture,
  bulletin: BulletinPicture,
  beacon: BeaconPicture,
  path: PathPicture,
  status: StatusPicture,
  range: RangePicture,
  request: RequestPicture,
};
