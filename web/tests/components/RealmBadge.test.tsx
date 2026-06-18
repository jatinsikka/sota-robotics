import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { RealmBadge } from "@/components/RealmBadge";
import { OriginBadge } from "@/components/OriginBadge";

describe("RealmBadge", () => {
  it("renders Sim with a sim data attribute", () => {
    render(<RealmBadge realm="sim" />);
    const el = screen.getByText("Sim");
    expect(el).toHaveAttribute("data-realm", "sim");
  });

  it("renders Real with a real data attribute", () => {
    render(<RealmBadge realm="real" />);
    expect(screen.getByText("Real")).toHaveAttribute("data-realm", "real");
  });
});

describe("OriginBadge", () => {
  it("renders the public origin label", () => {
    render(<OriginBadge origin="public_reproducible" />);
    const el = screen.getByText("Public · reproducible");
    expect(el).toHaveAttribute("data-origin", "public_reproducible");
  });

  it("renders the vendor origin label", () => {
    render(<OriginBadge origin="vendor_internal" />);
    expect(screen.getByText("Vendor · internal")).toHaveAttribute(
      "data-origin",
      "vendor_internal",
    );
  });
});
