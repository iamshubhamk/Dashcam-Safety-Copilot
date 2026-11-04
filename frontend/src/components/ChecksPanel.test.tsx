import { render, screen, within } from "@testing-library/react";
import { ChecksPanel } from "./ChecksPanel";

describe("ChecksPanel", () => {
  it("never shows a skipped or absent check as checked", () => {
    render(
      <ChecksPanel
        checks={{
          forward_collision: "ran",
          obstacle_in_lane: "absent",
          tailgating: "skipped_no_ego_speed",
          harsh_braking: "skipped_no_ego_speed",
          gps: "skipped_no_gps",
        }}
      />,
    );
    expect(within(screen.getByTestId("check-forward_collision")).getByText("Checked")).toBeInTheDocument();
    for (const key of ["obstacle_in_lane", "tailgating", "harsh_braking", "gps"]) {
      const row = within(screen.getByTestId(`check-${key}`));
      expect(row.getByText("Not checked")).toBeInTheDocument();
      expect(row.queryByText("Checked")).not.toBeInTheDocument();
    }
  });
});
