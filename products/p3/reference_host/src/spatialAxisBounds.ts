import type { SpatialMapV2 } from "../../contracts/spatial-map.v2";

export function spatialAxisBounds(geometry: Pick<SpatialMapV2["geometry"], "origin" | "radius">) {
  const { radius, origin } = geometry;
  return {
    x: { min: origin.x - radius, max: origin.x + radius },
    y: { min: origin.y - radius, max: origin.y + radius },
  };
}
