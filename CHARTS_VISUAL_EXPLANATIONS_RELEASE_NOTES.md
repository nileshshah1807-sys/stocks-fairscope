# Charts and Visual Explanations — Version 8.5

Implemented on 16 August 2026.

## New Visual analysis workspace

### Price vs valuation

- One-year market-price line
- Current blended fair-value reference
- Dynamic valuation-buffer reference
- Native-currency vertical scale
- Latest price marker
- Clear warning that current references are not historical fair values

### Model comparison

Horizontal bars compare:

- Sector-specific primary model
- Graham/book model
- Live peer model
- Blended fair value
- Current market price

Unavailable models are identified rather than drawn as zero.

### Fundamental trends

Separate sparklines show up to five annual observations for:

- Revenue
- Net income
- Free cash flow

Each series has its own scale, avoiding the misleading effect of plotting much smaller earnings on the same revenue axis.

### Scenario range and price position

- Conservative-to-optimistic valuation band
- Market-price marker
- Base fair-value marker
- Valuation-buffer marker
- Native-currency endpoints

## Improved existing visuals

### Sensitivity heatmap

- Green: modeled fair value above market price
- Amber: modeled fair value near market price
- Red: modeled fair value below market price
- Bold center cell: base discount-rate and terminal-growth assumptions
- Cell tooltips show fair value and percentage difference from market price

### Portfolio sector donut

- Sector weights displayed as a donut chart
- Up to six leading sectors shown in a color legend
- Existing exposure/stress table remains available for exact values

### PDF charts

Detailed stock reports now include:

- One-year price versus fair-value/valuation-buffer chart
- Base-model comparison bars
- Color-coded sensitivity heatmap
- Monte Carlo histogram with market-price marker
- Explanatory captions and limitations

## Implementation

Charts are drawn with native Qt `QPainter` and ReportLab vector graphics. No browser, external chart service, CDN, or Matplotlib runtime dependency is required.
