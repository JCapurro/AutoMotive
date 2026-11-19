import { describe, expect, it } from "vitest";

import { guessColumns } from "@/lib/dealer-sheet";
import { sheetKindOf, stockMedia, stockReadState, toBase64 } from "@/lib/dealer-stock-photo";

// What worker/intelligence/dealer_stock_read.py to_table() leaves in the job's output.
const OUTPUT = {
  read_id: 4, media_type: "image/jpeg", readable: true, rows_read: 2, truncated: false,
  headers: ["Marca", "Modelo", "Versión", "Año", "Km", "Precio", "Moneda", "Color"],
  rows: [["Ford", "Focus", "SE 1.6", "2017", "98000", "14500000", "ARS", "Gris"], ["Toyota", "Corolla", "", "2019", "", "18500", "USD"]],
};

describe("stock photo or PDF", () => {
  it("tells a photo or a PDF from a spreadsheet", () => {
    expect(stockMedia("lista.pdf", "")).toBe("application/pdf");
    expect(stockMedia("IMG_1.JPG", "")).toBe("image/jpeg");
    expect(stockMedia("x", "image/png")).toBe("image/png");
    expect(stockMedia("x.webp", null)).toBe("image/webp");
    expect(stockMedia("foto.heic", "image/heic")).toBe("image/jpeg");      // re-encoded in the browser
    expect(stockMedia("stock.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")).toBeNull();
    expect(stockMedia("stock.csv", "text/csv")).toBeNull();
    expect([sheetKindOf("application/pdf"), sheetKindOf("image/png")]).toEqual(["pdf", "photo"]);
  });

  it("encodes bytes as base64, also past a chunk", () => {
    expect(toBase64(new TextEncoder().encode("hola"))).toBe("aG9sYQ==");
    const big = new Uint8Array(0x8000 * 2 + 5).fill(65);
    expect(atob(toBase64(big)).length).toBe(big.length);
  });

  it("waits while the worker reads, then gives the spreadsheet table", () => {
    expect(stockReadState({ status: "queued", output: null })).toEqual({ state: "pending" });
    expect(stockReadState({ status: "running", output: null })).toEqual({ state: "pending" });
    const ok = stockReadState({ status: "done", output: OUTPUT });
    if (ok.state !== "ok") throw new Error(ok.state);
    expect(ok.kind).toBe("photo");
    expect(ok.table.rows[1]).toEqual(["Toyota", "Corolla", "", "2019", "", "18500", "USD", ""]);   // padded
    // The fixed headers map by themselves: the same preview as a CSV.
    expect(guessColumns(ok.table.headers, ok.table.rows)).toMatchObject({ make: 0, model: 1, trim: 2, year: 3, mileage_km: 4, price: 5, currency: 6 });
  });

  it("says why when nothing could be read", () => {
    expect(stockReadState({ status: "failed", output: null }).state).toBe("error");
    expect(stockReadState({ status: "done", output: { ...OUTPUT, readable: false } }).state).toBe("error");
    expect(stockReadState({ status: "done", output: { ...OUTPUT, rows: [] } }).state).toBe("error");
    expect(stockReadState(null).state).toBe("error");
  });
});
