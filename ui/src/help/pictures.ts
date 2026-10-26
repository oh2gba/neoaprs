// The pictures of the (i) notes by name: each is a component that draws one small picture (HelpFrame), so that InfoTip can show the one a note asks for.
import type { Component } from "vue";
import BeaconPicture from "@/help/BeaconPicture.vue";
import BulletinPicture from "@/help/BulletinPicture.vue";
import ObjectPicture from "@/help/ObjectPicture.vue";
import PathPicture from "@/help/PathPicture.vue";
import RangePicture from "@/help/RangePicture.vue";
import RequestPicture from "@/help/RequestPicture.vue";
import StatusPicture from "@/help/StatusPicture.vue";
import SsidPicture from "@/help/SsidPicture.vue";
import SymbolPicture from "@/help/SymbolPicture.vue";
import NetworkPicture from "@/help/NetworkPicture.vue";
import AccesskeyPicture from "@/help/AccesskeyPicture.vue";
import IgatePicture from "@/help/IgatePicture.vue";
import RadiusPicture from "@/help/RadiusPicture.vue";
import PositionPicture from "@/help/PositionPicture.vue";
import DigipeaterPicture from "@/help/DigipeaterPicture.vue";
import LogsPicture from "@/help/LogsPicture.vue";
import type { PictureName } from "@/help/names";

export const PICTURES: Record<PictureName, Component> = {
  object: ObjectPicture,
  bulletin: BulletinPicture,
  beacon: BeaconPicture,
  path: PathPicture,
  status: StatusPicture,
  range: RangePicture,
  request: RequestPicture,
  ssid: SsidPicture,
  symbol: SymbolPicture,
  network: NetworkPicture,
  accesskey: AccesskeyPicture,
  igate: IgatePicture,
  radius: RadiusPicture,
  position: PositionPicture,
  digipeater: DigipeaterPicture,
  logs: LogsPicture,
};
