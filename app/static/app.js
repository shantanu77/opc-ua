const { createApp, markRaw } = Vue;

createApp({
  data() {
    return {
      busy: false,
      notice: "Ready",
      pollHandle: null,
      chart: null,
      config: {
        endpoint: "opc.tcp://localhost:4840/freeopcua/server/",
        server_hostname: "localhost",
        namespace_uri: "http://example.org/opcua/simulator",
        namespace_nodeset_file: null,
        node_count: 100,
        update_interval_ms: 250,
        jitter_ms: 30,
        pattern: "random",
        min_value: 0,
        max_value: 100,
        noise_amplitude: 1,
        burst_probability: 0.07,
        burst_multiplier: 2.5,
        virtual_clients: 4,
        client_ops_per_sec: 8,
        test_duration_minutes: 0,
        load_profile: "constant",
        ramp_target_ops_per_sec: 20,
        ramp_duration_minutes: 10,
        step_interval_seconds: 60,
        step_increment_ops_per_sec: 1,
        spike_every_seconds: 120,
        spike_multiplier: 2,
        traffic_mix: {
          read_ratio: 0.45,
          write_ratio: 0.3,
          browse_ratio: 0.15,
          subscribe_ratio: 0.1,
        },
        fault_injection_enabled: false,
        fault_error_rate: 0.03,
        verbose_events: true,
        include_tracebacks: true,
        seed: 42,
      },
      status: {
        running: false,
        server_started: false,
        start_time: null,
        uptime_seconds: 0,
        run_duration_target_seconds: 0,
        remaining_seconds: 0,
        current_client_ops_per_sec: 0,
        load_profile: "constant",
        endpoint: "",
      },
      metrics: {
        total_operations: 0,
        ops_per_second: 0,
        current_client_ops_per_sec: 0,
        errors: 0,
        node_updates: 0,
        per_operation: {
          read: 0,
          write: 0,
          browse: 0,
          subscribe: 0,
        },
        timeline: [],
      },
      events: [],
      // Tab state
      activeTab: 'dashboard',
      // Namespace upload
      isDragOver: false,
      pendingFile: null,
      uploadedFileName: null,
      uploadBusy: false,
      uploadResult: null,
      namespaceInfo: {
        active_file: null,
        active_file_name: null,
        has_uploaded_file: false,
        configured_file: null,
        namespace_uri: '',
      },
      // Log filter
      logLevelFilter: '',
      logSearch: '',
    };
  },
  computed: {
    ratioSum() {
      const mix = this.config.traffic_mix;
      return mix.read_ratio + mix.write_ratio + mix.browse_ratio + mix.subscribe_ratio;
    },
    ratioValid() {
      return Math.abs(this.ratioSum - 1) < 0.000001;
    },
    filteredEvents() {
      let items = this.events;
      if (this.logLevelFilter) {
        items = items.filter((e) => e.level === this.logLevelFilter);
      }
      if (this.logSearch.trim()) {
        const q = this.logSearch.trim().toLowerCase();
        items = items.filter((e) => e.message.toLowerCase().includes(q));
      }
      return items;
    },
    errorCount() {
      return this.events.filter((e) => e.level === 'ERROR').length;
    },
  },
  methods: {
    async api(path, options = {}) {
      const response = await fetch(path, {
        headers: { "Content-Type": "application/json" },
        ...options,
      });

      if (!response.ok) {
        const errorBody = await response.text();
        throw new Error(errorBody || `Request failed with ${response.status}`);
      }

      return response.json();
    },
    setNotice(message) {
      this.notice = message;
    },
    formatSeconds(value) {
      const s = Math.floor(value || 0);
      const hours = String(Math.floor(s / 3600)).padStart(2, "0");
      const mins = String(Math.floor((s % 3600) / 60)).padStart(2, "0");
      const secs = String(s % 60).padStart(2, "0");
      return `${hours}:${mins}:${secs}`;
    },
    formatTs(value) {
      if (!value) return "-";
      return new Date(value).toLocaleTimeString();
    },
    initChart() {
      const ctx = document.getElementById("opsChart");
      this.chart = markRaw(new Chart(ctx, {
        type: "line",
        data: {
          labels: [],
          datasets: [
            {
              label: "Ops Last Sec",
              data: [],
              borderColor: "#13c4a3",
              backgroundColor: "rgba(19, 196, 163, 0.2)",
              tension: 0.3,
            },
            {
              label: "Errors Last Sec",
              data: [],
              borderColor: "#ff6b57",
              backgroundColor: "rgba(255, 107, 87, 0.2)",
              tension: 0.25,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          scales: {
            x: {
              ticks: { color: "#dbe7df" },
              grid: { color: "rgba(255, 255, 255, 0.06)" },
            },
            y: {
              ticks: { color: "#dbe7df" },
              grid: { color: "rgba(255, 255, 255, 0.06)" },
            },
          },
          plugins: {
            legend: {
              labels: { color: "#e3ece5" },
            },
          },
        },
      }));
    },
    refreshChart() {
      if (!this.chart) return;

      const timeline = this.metrics.timeline || [];
      const recent = timeline.slice(-40);
      this.chart.data.labels = recent.map((point) => this.formatTs(point.ts));
      this.chart.data.datasets[0].data = recent.map((point) => point.ops_last_sec || 0);
      this.chart.data.datasets[1].data = recent.map((point) => point.errors_last_sec || 0);
      this.chart.update();
    },
    async loadConfig() {
      this.config = await this.api("/api/simulator/config");
    },
    async loadStatus() {
      this.status = await this.api("/api/simulator/status");
    },
    async loadMetrics() {
      this.metrics = await this.api("/api/simulator/metrics");
      this.refreshChart();
    },
    async loadEvents() {
      const items = await this.api("/api/simulator/events");
      this.events = items.slice().reverse().slice(0, 80);
    },
    async saveConfig() {
      if (!this.ratioValid) {
        this.setNotice("Traffic ratios must sum to 1.00");
        return;
      }

      this.busy = true;
      try {
        this.config = await this.api("/api/simulator/config", {
          method: "PUT",
          body: JSON.stringify(this.config),
        });
        this.setNotice("Configuration saved");
      } catch (err) {
        this.setNotice(`Failed to save configuration: ${err.message}`);
      } finally {
        this.busy = false;
      }
    },
    async startSimulator() {
      if (!this.ratioValid) {
        this.setNotice("Traffic ratios must sum to 1.00");
        return;
      }

      this.busy = true;
      try {
        await this.saveConfig();
        await this.api("/api/simulator/start", { method: "POST" });
        await this.reloadData();
        this.setNotice("Simulator started");
      } catch (err) {
        this.setNotice(`Unable to start simulator: ${err.message}`);
      } finally {
        this.busy = false;
      }
    },
    async stopSimulator() {
      this.busy = true;
      try {
        await this.api("/api/simulator/stop", { method: "POST" });
        await this.reloadData();
        this.setNotice("Simulator stopped");
      } catch (err) {
        this.setNotice(`Unable to stop simulator: ${err.message}`);
      } finally {
        this.busy = false;
      }
    },
    async reloadData() {
      await Promise.all([this.loadStatus(), this.loadMetrics(), this.loadEvents(), this.loadNamespaceInfo()]);
    },
    startPolling() {
      this.pollHandle = setInterval(async () => {
        try {
          await this.reloadData();
        } catch (err) {
          this.setNotice(`Refresh error: ${err.message}`);
        }
      }, 1000);
    },

    async loadNamespaceInfo() {
      try {
        this.namespaceInfo = await this.api('/api/namespace/info');
      } catch (_) {
        // non-critical
      }
    },

    handleFileSelect(event) {
      const file = event.target.files[0];
      if (file) {
        this.pendingFile = file;
        this.uploadedFileName = file.name;
        this.uploadResult = null;
      }
    },

    handleFileDrop(event) {
      const file = event.dataTransfer.files[0];
      if (file) {
        if (!file.name.toLowerCase().endsWith('.xml')) {
          this.setNotice('Only .xml files are accepted');
          return;
        }
        this.pendingFile = file;
        this.uploadedFileName = file.name;
        this.uploadResult = null;
        this.isDragOver = false;
      }
    },

    async uploadNamespaceFile() {
      if (!this.pendingFile) return;
      this.uploadBusy = true;
      this.uploadResult = null;
      try {
        const formData = new FormData();
        formData.append('file', this.pendingFile);
        const response = await fetch('/api/namespace/upload', { method: 'POST', body: formData });
        if (!response.ok) {
          const body = await response.text();
          throw new Error(body || `Upload failed (${response.status})`);
        }
        const data = await response.json();
        this.uploadResult = { ok: true, message: `Uploaded: ${data.filename}` };
        this.pendingFile = null;
        await this.loadNamespaceInfo();
        this.setNotice(`Namespace file uploaded: ${data.filename}`);
      } catch (err) {
        this.uploadResult = { ok: false, message: err.message };
        this.setNotice(`Upload failed: ${err.message}`);
      } finally {
        this.uploadBusy = false;
      }
    },

    async clearNamespaceFile() {
      try {
        await this.api('/api/namespace/file', { method: 'DELETE' });
        this.uploadedFileName = null;
        this.pendingFile = null;
        this.uploadResult = null;
        await this.loadNamespaceInfo();
        this.setNotice('Uploaded namespace file removed');
      } catch (err) {
        this.setNotice(`Clear failed: ${err.message}`);
      }
    },

    clearLogFilter() {
      this.logLevelFilter = '';
      this.logSearch = '';
    },
  },
  async mounted() {
    this.initChart();

    try {
      await this.loadConfig();
      await this.reloadData();
      this.startPolling();
      this.setNotice("Connected");
    } catch (err) {
      this.setNotice(`Initialization error: ${err.message}`);
    }
  },
  beforeUnmount() {
    if (this.pollHandle) {
      clearInterval(this.pollHandle);
    }
  },
}).mount("#app");
