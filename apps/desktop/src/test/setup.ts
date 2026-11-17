import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => {
  cleanup();
});

// jsdom does not implement scrolling.
Element.prototype.scrollIntoView = function scrollIntoView() {
  /* no-op in tests */
};
