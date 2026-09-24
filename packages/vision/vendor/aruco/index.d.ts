export declare const AR: {
  Detector: new (config?: { dictionaryName?: string; maxHammingDistance?: number }) => {
    detect(image: { width: number; height: number; data: Uint8ClampedArray | Uint8Array }): { id: number; corners: { x: number; y: number }[]; hammingDistance: number }[];
  };
};
