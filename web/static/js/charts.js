// Plotly Chart Rendering Helper with Auto-Resize
function renderPlotlyChart(containerId, chartJsonString) {
    const container = document.getElementById(containerId);
    if (!container || !chartJsonString) return;

    try {
        const figure = typeof chartJsonString === "string" ? JSON.parse(chartJsonString) : chartJsonString;
        
        // Ensure responsive layout config
        const config = { responsive: true, displayModeBar: false };
        
        Plotly.newPlot(containerId, figure.data, figure.layout, config);

        // Window resize listener
        window.addEventListener("resize", function () {
            Plotly.Plots.resize(container);
        });
    } catch (err) {
        console.error("Failed to render Plotly chart on #" + containerId, err);
    }
}
