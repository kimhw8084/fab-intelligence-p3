import { describe, expect, it } from "vitest";
import { spatialAxisBounds } from "./spatialAxisBounds";

describe("physical wafer plot bounds", () => {
  it("centers the physical radius around the verified coordinate origin", () => {
    expect(spatialAxisBounds({ origin: { x: 12, y: -7 }, radius: 4 })).toEqual({
      x: { min: 8, max: 16 },
      y: { min: -11, max: -3 },
    });
  });
});
