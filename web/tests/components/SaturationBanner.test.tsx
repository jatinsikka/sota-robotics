import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { SaturationBanner } from "@/components/SaturationBanner";

describe("SaturationBanner", () => {
  it("renders a warning when the benchmark is saturated", () => {
    render(<SaturationBanner isSaturated={true} benchmarkName="LIBERO" />);
    const banner = screen.getByRole("alert");
    expect(banner).toHaveTextContent(/saturated/i);
    expect(banner).toHaveTextContent("LIBERO");
  });

  it("renders nothing when not saturated", () => {
    const { container } = render(
      <SaturationBanner isSaturated={false} benchmarkName="RoboArena" />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
