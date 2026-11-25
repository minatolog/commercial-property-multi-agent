(() => {
  const stylesheet = new URL("mall-hologram.css", document.currentScript.src).href;
  const floors = [1, 2, 3];
  const shops = [
    { id: "A-101", floor: 1, name: "星汇优选", category: "生活零售", angle: .65, agents: ["商户", "客流"], note: "营业正常。商户 Agent 正跟进午后客流变化。" },
    { id: "A-102", floor: 1, name: "光合花房", category: "鲜花零售", angle: 1.89, agents: ["商户"], note: "营业正常。商户 Agent 已完成今日营业检查。" },
    { id: "A-103", floor: 1, name: "城市便利", category: "便利零售", angle: 3.22, agents: ["商户"], note: "营业正常。当前无待处理事项。" },
    { id: "A-104", floor: 1, name: "晨光烘焙", category: "餐饮", angle: 4.75, agents: ["商户", "营销"], note: "营业正常。营销 Agent 正跟进新品活动。" },
    { id: "A-201", floor: 2, name: "山野户外", category: "运动零售", angle: .65, agents: ["商户"], note: "营业正常。当前无待处理事项。" },
    { id: "A-202", floor: 2, name: "拾光书店", category: "书店", angle: 1.89, agents: ["商户", "营销"], note: "营业正常。营销 Agent 正整理活动到店数据。" },
    { id: "A-203", floor: 2, name: "小岛玩具", category: "亲子零售", angle: 3.22, agents: ["商户", "客流"], note: "营业正常。客流 Agent 正监测店前通道。" },
    { id: "A-204", floor: 2, name: "留白生活", category: "家居零售", angle: 4.75, agents: ["商户"], note: "营业正常。当前无待处理事项。" },
    { id: "A-301", floor: 3, name: "云端咖啡", category: "餐饮", angle: .65, agents: ["合同", "账单", "物业"], watch: true, note: "租金金额与空调维修存在争议，可交由合同、账单及物业 Agent 核验。" },
    { id: "A-302", floor: 3, name: "星汇文具", category: "文具零售", angle: 1.89, agents: ["合同", "账单"], note: "可通过合同或账单 Agent 核验租约和缴费情况。" },
    { id: "A-303", floor: 3, name: "南岸轻食", category: "餐饮", angle: 3.22, agents: ["商户", "营销"], note: "营业正常。营销 Agent 正跟进餐饮券核销。" },
    { id: "A-304", floor: 3, name: "茶序", category: "餐饮", angle: 4.75, agents: ["商户", "客流"], note: "营业正常。客流 Agent 正跟进高峰排队。" },
  ];
  const icons = {
    model: '<path d="M12 2.8 21 8v8l-9 5.2L3 16V8zm0 10.3L3 8m9 5.1L21 8m-9 5.1v8.1"/>',
    top: '<path d="M5 9V5h4m6 0h4v4m0 6v4h-4m-6 0H5v-4"/><rect x="9" y="9" width="6" height="6" rx="1"/>',
    reset: '<path d="M3 12a9 9 0 1 0 3-6.7L3 8m0-5v5h5"/>',
    plus: '<path d="M6 12h12m-6-6v12"/>',
    minus: '<path d="M6 12h12"/>',
  };
  const svg = (name) => '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + icons[name] + '</svg>';
  const orbit = { yaw: -.20, pitch: .55, zoom: 1, gap: 1.14 };
  const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
  const tau = Math.PI * 2;
  const oval = (angle, radius, y) => [4.65 * radius * Math.cos(angle), y, 3.15 * radius * Math.sin(angle)];
  const propLabel = (shop) => shop.id + " " + shop.name;
  const control = (command, label, face, toggle = false) =>
    `<button type="button" class="control" data-command="${command}" title="${label}" aria-label="${label}"${toggle ? ' aria-pressed="false"' : ''}>${face}</button>`;

  class MallHologram extends HTMLElement {
    connectedCallback() {
      if (!this.shadowRoot) this.build();
      this.observer.observe(this.viewport);
    }

    disconnectedCallback() {
      this.observer.disconnect();
      cancelAnimationFrame(this.frame);
      this.frame = 0;
    }

    build() {
      this.floor = 0;
      this.selected = shops.find((shop) => shop.id === "A-301");
      this.camera = { ...orbit };
      this.target = { ...orbit };
      this.motion = matchMedia("(prefers-reduced-motion: reduce)");
      this.pointers = new Map();
      const root = this.attachShadow({ mode: "open" });
      root.innerHTML = `
        <link rel="stylesheet" href="${stylesheet}">
        <section class="rig" aria-labelledby="mall-heading">
          <header class="heading"><div class="title">${svg("model")}<div><h2 id="mall-heading">商场实时态势</h2><p class="site">星汇广场 · 3D 楼层视图</p></div></div><span class="demo">模拟数据</span></header>
          <div class="layout">
            <div class="viewport">
              <canvas tabindex="0" aria-label="3D 商场模型" aria-describedby="view-note"></canvas>
              <p class="model-unavailable" hidden>3D 视图暂不可用，可以从商铺列表查看详情。</p>
              <div class="pins"></div>
              <div class="floorbar" role="group" aria-label="查看楼层">
                <button type="button" class="control" data-floor="0" aria-pressed="true">全场</button>
                ${floors.map((floor) => `<button type="button" class="control" data-floor="${floor}" aria-pressed="false">L${floor}</button>`).join("")}
                ${control("explode", "展开楼层", "展开楼层", true)}
              </div>
              <p class="view-note" id="view-note">拖动旋转 · 滚轮或双指缩放</p>
              <div class="viewbar" role="group" aria-label="模型视角">
                ${control("top", "俯视视角", svg("top"), true)}
                ${control("in", "放大", svg("plus"))}
                ${control("out", "缩小", svg("minus"))}
                ${control("reset", "重置视角", svg("reset"))}
              </div>
            </div>
            <section class="inspector" aria-labelledby="shops-heading">
              <header class="shop-header"><h3 id="shops-heading">商铺查看</h3><span class="shop-count"></span></header>
              <div class="shops" role="group" aria-label="商铺列表"></div>
              <div class="detail" aria-live="polite">
                <div class="shop-name"><strong></strong><span class="shop-status"></span></div>
                <p class="shop-meta"></p><p class="shop-summary"></p>
                <div class="shop-actions">
                  <div class="agent-list" aria-label="相关 Agent"></div>
                  <button type="button" class="shop-action" hidden>发起商铺协同</button>
                  <a class="shop-action shop-investigation" hidden>新建商铺调查</a>
                </div>
              </div>
            </section>
          </div>
          <slot name="events"></slot>
        </section>`;
      const site = this.getAttribute("property-name") || "星汇广场";
      root.querySelector(".site").textContent = site + " · 3D 楼层视图";
      this.viewport = root.querySelector(".viewport");
      this.canvas = root.querySelector("canvas");
      this.context = this.canvas.getContext("2d");
      this.pins = root.querySelector(".pins");
      if (!this.context) {
        this.canvas.hidden = true;
        root.querySelector(".model-unavailable").hidden = false;
        root.querySelector(".viewbar").hidden = true;
        root.querySelector(".view-note").hidden = true;
      }
      root.addEventListener("click", (event) => this.onControl(event));
      this.bindCamera();
      this.updateControls();
      this.observer = new ResizeObserver(([entry]) => {
        const { width, height } = entry.contentRect;
        if (!width || !height || !this.context) return;
        const ratio = Math.min(devicePixelRatio || 1, 2);
        this.width = width;
        this.height = height;
        this.canvas.width = Math.round(width * ratio);
        this.canvas.height = Math.round(height * ratio);
        this.context.setTransform(ratio, 0, 0, ratio, 0, 0);
        this.invalidate();
      });
    }

    onControl(event) {
      const button = event.target.closest("button");
      if (!button) return;
      const { floor, shop, command } = button.dataset;
      if (floor !== undefined) {
        this.floor = Number(floor);
        if (this.floor && this.selected.floor !== this.floor) this.selected = shops.find((item) => item.floor === this.floor);
        this.updateControls();
        this.dispatchEvent(new CustomEvent("mall-floor-change", { bubbles: true, detail: { floor: this.floor } }));
      } else if (shop) {
        this.selectShop(shops.find((item) => item.id === shop));
      } else if (button.classList.contains("shop-action")) {
        this.dispatchEvent(new CustomEvent("mall-shop-action", {
          bubbles: true, detail: { id: this.selected.id, name: this.selected.name },
        }));
      } else if (command === "explode") {
        this.target.gap = this.target.gap === orbit.gap ? 2.15 : orbit.gap;
        this.updateControls();
      } else if (command === "top") {
        this.target.pitch = this.target.pitch > 1.4 ? orbit.pitch : Math.PI / 2;
        this.updateControls();
      } else if (command === "reset") {
        this.target = { ...orbit };
        this.updateControls();
      } else if (command === "in" || command === "out") {
        this.zoomBy(command === "in" ? 1.18 : 1 / 1.18);
      }
    }

    get visibleShops() {
      return this.floor ? shops.filter((shop) => shop.floor === this.floor) : shops;
    }

    selectShop(shop) {
      if (!shop || shop === this.selected) return;
      this.selected = shop;
      this.updateControls();
    }

    updateControls() {
      const root = this.shadowRoot;
      const shopsList = root.querySelector(".shops");
      const detail = root.querySelector(".detail");
      const shop = this.selected;
      root.querySelectorAll("[data-floor]").forEach((button) => button.setAttribute("aria-pressed", Number(button.dataset.floor) === this.floor));
      const explode = root.querySelector('[data-command="explode"]');
      explode.disabled = Boolean(this.floor) || !this.context;
      explode.setAttribute("aria-pressed", !this.floor && this.target.gap !== orbit.gap);
      root.querySelector('[data-command="top"]').setAttribute("aria-pressed", this.target.pitch > 1.4);
      root.querySelector(".shop-count").textContent = this.visibleShops.length + " 间商铺";
      if (this.listFloor !== this.floor) {
        this.listFloor = this.floor;
        shopsList.innerHTML = this.visibleShops.map((item) => `<button type="button" class="control shop-button" data-shop="${item.id}" aria-label="${propLabel(item)}" title="${propLabel(item)}">${item.id}</button>`).join("");
        this.pins.innerHTML = this.context ? this.visibleShops.map((item) => `<button type="button" class="pin" data-shop="${item.id}" aria-label="在模型中查看 ${propLabel(item)}"><span></span>${item.id}</button>`).join("") : "";
      }
      root.querySelectorAll("[data-shop]").forEach((button) => button.setAttribute("aria-pressed", button.dataset.shop === shop.id));
      detail.querySelector(".shop-name strong").textContent = shop.name;
      const status = detail.querySelector(".shop-status");
      status.textContent = shop.watch ? "需关注" : "营业正常";
      status.dataset.watch = Boolean(shop.watch);
      detail.querySelector(".shop-meta").textContent = `L${shop.floor} · ${shop.id} · ${shop.category}`;
      const overview = this.getAttribute("action") === "coordinate";
      const summary = overview && shop.id === "A-301" ? "商户 Agent 已登记租金和空调报修反馈，可发起商铺运营核查。"
        : overview && shop.id === "A-302" ? "营业正常。商户 Agent 可跟进租约和经营情况。" : shop.note;
      const agents = overview && shop.floor === 3 && ["A-301", "A-302"].includes(shop.id) ? ["商户", "设施"] : shop.agents;
      detail.querySelector(".shop-summary").textContent = summary;
      detail.querySelector(".agent-list").innerHTML = agents.map((agent) => "<span>" + agent + " Agent</span>").join("");
      detail.querySelector("button.shop-action").hidden = !overview;
      const investigationPath = this.getAttribute("investigation-path");
      const investigation = detail.querySelector(".shop-investigation");
      investigation.hidden = !investigationPath || !["A-301", "A-302"].includes(shop.id);
      if (!investigation.hidden) investigation.href = investigationPath + "?" + new URLSearchParams({ store: shop.id });
      this.invalidate();
    }

    bindCamera() {
      const canvas = this.canvas;
      if (!this.context) return;
      canvas.addEventListener("pointerdown", (event) => {
        if (event.button !== 0 || this.pointers.size === 2) return;
        if (!this.pointers.size) this.dragged = false;
        this.pointers.set(event.pointerId, { x: event.clientX, y: event.clientY, originX: event.clientX, originY: event.clientY });
        if (this.pointers.size === 2) this.dragged = true;
        canvas.setPointerCapture(event.pointerId);
      });
      canvas.addEventListener("pointermove", (event) => {
        const point = this.pointers.get(event.pointerId);
        if (!point) {
          if (event.pointerType === "mouse") canvas.classList.toggle("is-picking", Boolean(this.hit(event)));
          return;
        }
        const before = this.pinchDistance();
        const dx = event.clientX - point.x;
        const dy = event.clientY - point.y;
        point.x = event.clientX;
        point.y = event.clientY;
        if (Math.hypot(point.x - point.originX, point.y - point.originY) > 4) this.dragged = true;
        if (!this.dragged) return;
        canvas.classList.add("is-dragging");
        if (before > 0) this.zoomBy(this.pinchDistance() / before);
        else this.rotate(dx * .009, dy * .008);
      });
      const release = (event) => {
        if (!this.pointers.delete(event.pointerId)) return;
        if (!this.dragged && event.type === "pointerup") this.selectShop(this.hit(event));
        if (!this.pointers.size) canvas.classList.remove("is-dragging");
      };
      for (const type of ["pointerup", "pointercancel", "lostpointercapture"]) canvas.addEventListener(type, release);
      canvas.addEventListener("wheel", (event) => {
        event.preventDefault();
        this.zoomBy(Math.exp(-clamp(event.deltaY, -160, 160) * (event.deltaMode ? .023 : .0019)));
      }, { passive: false });
      canvas.addEventListener("keydown", (event) => {
        const keys = {
          ArrowLeft: () => this.rotate(-.12, 0), ArrowRight: () => this.rotate(.12, 0),
          ArrowUp: () => this.rotate(0, .10), ArrowDown: () => this.rotate(0, -.10),
          "+": () => this.zoomBy(1.18), "=": () => this.zoomBy(1.18), "-": () => this.zoomBy(1 / 1.18),
        };
        if (!keys[event.key]) return;
        event.preventDefault();
        keys[event.key]();
      });
    }

    pinchDistance() {
      if (this.pointers.size < 2) return 0;
      const [a, b] = this.pointers.values();
      return Math.hypot(a.x - b.x, a.y - b.y);
    }

    zoomBy(ratio) {
      this.target.zoom = clamp(this.target.zoom * ratio, .70, 1.46);
      this.invalidate();
    }

    rotate(yaw, pitch) {
      this.target.yaw += yaw;
      this.target.pitch = clamp(this.target.pitch + pitch, .12, Math.PI / 2);
      this.shadowRoot.querySelector('[data-command="top"]').setAttribute("aria-pressed", this.target.pitch > 1.4);
      this.invalidate();
    }

    invalidate() {
      if (this.frame || !this.context || !this.width) return;
      this.frame = requestAnimationFrame(() => {
        this.frame = 0;
        let moving = false;
        for (const key of Object.keys(this.target)) {
          const delta = this.target[key] - this.camera[key];
          if (this.motion.matches || Math.abs(delta) < .001) this.camera[key] = this.target[key];
          else {
            this.camera[key] += delta * .27;
            moving = true;
          }
        }
        this.renderModel();
        if (moving) this.invalidate();
      });
    }

    projector() {
      const { yaw, pitch, zoom } = this.camera;
      const sinYaw = Math.sin(yaw), cosYaw = Math.cos(yaw);
      const sinPitch = Math.sin(pitch), cosPitch = Math.cos(pitch);
      const scale = Math.min(this.width / 12.3, this.height / 8.6) * zoom;
      return ([x, y, z]) => {
        const across = cosYaw * x - sinYaw * z;
        const forward = sinYaw * x + cosYaw * z;
        const depth = sinPitch * y + cosPitch * forward;
        const perspective = 18 / (18 - depth);
        return [this.width / 2 + across * scale * perspective,
          this.height * .52 - (cosPitch * y - sinPitch * forward) * scale * perspective, depth];
      };
    }

    renderModel() {
      const ctx = this.context;
      const project = this.projector();
      const height = (floor) => this.floor ? 0 : (floor - 2) * this.camera.gap;
      const ground = height(1) - .92;
      const faces = [];
      const add = (corners, fill, edge, shop = null, halo = false) => {
        const points = corners.map(project);
        const depth = points.reduce((sum, point) => sum + point[2], 0) / points.length;
        const face = { points, depth, fill, edge, shop, halo };
        faces.push(face);
        return face;
      };
      const segment = (first, second, inside, outside, y) =>
        [oval(first, inside, y), oval(first, outside, y), oval(second, outside, y), oval(second, inside, y)];
      ctx.clearRect(0, 0, this.width, this.height);
      this.drawGrid(project, ground);

      for (const floor of this.floor ? [this.floor] : floors) {
        const y = height(floor);
        for (let index = 0; index < 44; index++) {
          const a = index * tau / 44, b = (index + 1) * tau / 44;
          add(segment(a, b, .47, 1, y), index % 2 ? "#0c303f" : "#0c3444", "#246077");
          add([oval(a, 1, y), oval(b, 1, y), oval(b, 1, y - .18), oval(a, 1, y - .18)], "#10394a", "#3995ac");
          add([oval(a, .47, y + .10), oval(b, .47, y + .10), oval(b, .47, y), oval(a, .47, y)], "#154458", "#4aabc1");
        }
        for (const angle of [.24, 1.57, 2.88, 4.03, 5.46]) {
          add([oval(angle, .46, y - .88), oval(angle + .025, .46, y - .88), oval(angle + .025, .46, y), oval(angle, .46, y)], "#153a4a", "#386a7b");
        }
        if (floor > 1) this.drawEscalator(y, add);
      }

      for (const shop of this.visibleShops) {
        const y = height(shop.floor);
        const active = this.selected === shop;
        const a = shop.angle - .33, b = shop.angle + .33;
        const lower = segment(a, b, .60, .94, y + .05);
        const upper = segment(a, b, .60, .94, y + .70);
        const edge = active ? "#ffd09b" : "#4ab9d1";
        add(upper, active ? "#76492b" : "#17536a", edge, shop, active);
        for (let index = 0; index < 4; index++) {
          const next = (index + 1) % 4;
          const wall = [lower[index], lower[next], upper[next], upper[index]];
          const panel = add(wall, active ? "#503221" : index % 2 ? "#103849" : "#0d2a3d", edge, shop);
          const facade = (part, elevation) => lower[index].map((axis, i) =>
            axis + (lower[next][i] - axis) * part + (i === 1 ? elevation : 0));
          panel.windows = [.12, .39, .66].map((part) =>
            [facade(part, .09), facade(part + .22, .09), facade(part + .22, .40), facade(part, .40)].map(project));
        }
      }

      faces.sort((a, b) => a.depth - b.depth);
      for (const face of faces) {
        this.paint(face.points, face.fill, face.edge, face.halo);
        for (const window of face.windows || []) {
          const selected = face.shop === this.selected;
          this.paint(window, selected ? "#a36a3d" : "#22667b", selected ? "#d0955e" : "#418ea2");
        }
      }
      this.drawnFaces = faces.reverse();
      this.positionPins(project, height);
    }

    drawEscalator(y, add) {
      const start = -1.3, width = .36, step = .16, height = .11, z = -.53;
      for (let i = 0; i < 9; i++) {
        const x = start + i * step, next = x + step, top = y - i * height;
        add([[x, top, z], [next, top, z], [next, top, z + width], [x, top, z + width]], "#194b60", "#59b2c7");
        add([[next, top, z], [next, top, z + width], [next, top - height, z + width], [next, top - height, z]], "#154353", "#2d748c");
      }
      const end = start + 9 * step, bottom = y - 9 * height;
      for (const side of [z, z + width]) {
        add([[start, y, side], [end, bottom, side], [end, bottom + .2, side], [start, y + .2, side]], "#184759", "#65c5d6");
      }
    }

    paint(points, fill, edge, halo = false) {
      const ctx = this.context;
      ctx.beginPath();
      ctx.moveTo(points[0][0], points[0][1]);
      for (const [x, y] of points.slice(1)) ctx.lineTo(x, y);
      ctx.closePath();
      if (fill) {
        ctx.fillStyle = fill;
        ctx.fill();
      }
      ctx.lineWidth = .75;
      ctx.strokeStyle = edge;
      if (halo) {
        ctx.shadowColor = edge;
        ctx.shadowBlur = 11;
      }
      ctx.stroke();
      if (halo) ctx.shadowBlur = 0;
    }

    drawGrid(project, y) {
      const ctx = this.context;
      const radial = (radius, angle) => [Math.cos(angle) * radius, y, Math.sin(angle) * radius];
      for (const radius of [2.0, 3.7, 4.8, 5.05, 5.7]) {
        const points = Array.from({ length: 72 }, (_, index) => project(radial(radius, index * tau / 72)));
        this.paint(points, null, radius === 4.8 ? "#387d95" : "#205066");
      }
      ctx.beginPath();
      for (let index = 0; index < 48; index++) {
        const a = index * tau / 48;
        const from = project(radial(index % 4 ? 4.9 : 4.65, a)), to = project(radial(5.05, a));
        ctx.moveTo(from[0], from[1]);
        ctx.lineTo(to[0], to[1]);
      }
      ctx.lineWidth = 1;
      ctx.strokeStyle = "#438ca4";
      ctx.stroke();
    }

    positionPins(project, height) {
      const placed = [];
      const visible = this.visibleShops.filter((shop) => this.floor || shop.floor === 3 || shop === this.selected)
        .sort((a, b) => Number(b === this.selected) - Number(a === this.selected));
      for (const shop of visible) {
        const [x, pinY] = project(oval(shop.angle, .80, height(shop.floor) + .75));
        const y = pinY - 8;
        if (x >= 32 && y >= 80 && x <= this.width - 32 && y <= this.height - 43 &&
          !placed.some((point) => Math.abs(point.x - x) < 60 && Math.abs(point.y - y) < 26)) {
          placed.push({ id: shop.id, x, y });
        }
      }
      for (const pin of this.pins.children) {
        const point = placed.find((entry) => entry.id === pin.dataset.shop);
        pin.hidden = !point;
        if (!point) continue;
        pin.style.left = point.x + "px";
        pin.style.top = point.y + "px";
      }
    }

    hit(event) {
      const rect = this.canvas.getBoundingClientRect();
      const x = event.clientX - rect.left, y = event.clientY - rect.top;
      return this.drawnFaces?.find(({ points }) => {
        let inside = false;
        for (let i = 0, j = points.length - 1; i < points.length; j = i++) {
          const [ax, ay] = points[i], [bx, by] = points[j];
          if ((ay > y) !== (by > y) && x < (bx - ax) * (y - ay) / (by - ay) + ax) inside = !inside;
        }
        return inside;
      })?.shop;
    }
  }

  customElements.define("mall-hologram", MallHologram);
})();
