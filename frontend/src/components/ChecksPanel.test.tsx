import { render, screen, within } from "@testing-library/react";
import { ChecksPanel } from "./ChecksPanel";
import { checkRows } from "../lib/display";
import { DEMO_TRIP_2, seedReports } from "../mocks/fixtures";

describe("ChecksPanel", () => {
  it("never shows a skipped or absent check as checked", () => {
    const report = seedReports[DEMO_TRIP_2]!;
    render(<ChecksPanel rows={checkRows(report.not_checked, false)} />);
    expect(within(screen.getByTestId("check-forward_collision")).getByText("Checked")).toBeInTheDocument();
    for (const n of report.not_checked) {
      const row = within(screen.getByTestId(`check-${n.type}`));
      expect(row.getByText("Not checked")).toBeInTheDocument();
      expect(row.getByText(n.reason)).toBeInTheDocument();
      expect(row.queryByText("Checked")).not.toBeInTheDocument();
    }
  });
});
