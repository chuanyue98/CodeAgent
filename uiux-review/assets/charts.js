(function() {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var bg2 = style.getPropertyValue('--bg2').trim();
  var danger = style.getPropertyValue('--danger').trim();
  var warn = style.getPropertyValue('--warn').trim();

  // === Chart 1: Issues by Area (Stacked Bar) ===
  var chart1 = echarts.init(document.getElementById('chart-area'), null, { renderer: 'svg' });
  chart1.setOption({
    animation: false,
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      appendToBody: true,
      textStyle: { fontSize: 12 }
    },
    legend: {
      data: ['P0 高优先级', 'P1 中优先级', 'P2 低优先级'],
      bottom: 0,
      textStyle: { color: muted, fontSize: 11 },
      itemWidth: 12,
      itemHeight: 12,
      itemGap: 16
    },
    grid: { left: '3%', right: '4%', bottom: '15%', top: '8%', containLabel: true },
    xAxis: {
      type: 'category',
      data: ['Web UI 前端', 'Web API 后端', 'CLI 交互'],
      axisLine: { lineStyle: { color: rule } },
      axisLabel: { color: ink, fontSize: 12, fontWeight: 600 },
      axisTick: { show: false }
    },
    yAxis: {
      type: 'value',
      max: 16,
      axisLine: { show: false },
      axisLabel: { color: muted, fontSize: 11 },
      splitLine: { lineStyle: { color: rule, type: 'dashed' } }
    },
    series: [
      {
        name: 'P0 高优先级',
        type: 'bar',
        stack: 'total',
        data: [4, 1, 0],
        itemStyle: { color: danger, borderRadius: [0, 0, 0, 0] },
        barWidth: '40%'
      },
      {
        name: 'P1 中优先级',
        type: 'bar',
        stack: 'total',
        data: [6, 3, 0],
        itemStyle: { color: warn }
      },
      {
        name: 'P2 低优先级',
        type: 'bar',
        stack: 'total',
        data: [5, 3, 2],
        itemStyle: { color: accent2, borderRadius: [4, 4, 0, 0] }
      }
    ]
  });
  window.addEventListener('resize', function() { chart1.resize(); });

  // === Chart 2: Severity Distribution (Pie) ===
  var chart2 = echarts.init(document.getElementById('chart-severity'), null, { renderer: 'svg' });
  chart2.setOption({
    animation: false,
    tooltip: {
      trigger: 'item',
      appendToBody: true,
      formatter: '{b}: {c} 个 ({d}%)',
      textStyle: { fontSize: 12 }
    },
    legend: {
      bottom: 0,
      textStyle: { color: muted, fontSize: 11 },
      itemWidth: 12,
      itemHeight: 12,
      itemGap: 16
    },
    series: [{
      type: 'pie',
      radius: ['40%', '65%'],
      center: ['50%', '42%'],
      avoidLabelOverlap: true,
      itemStyle: {
        borderRadius: 6,
        borderColor: '#fff',
        borderWidth: 3
      },
      label: {
        show: true,
        color: ink,
        fontSize: 12,
        fontWeight: 600,
        formatter: '{b}\n{c} 个'
      },
      labelLine: {
        length: 12,
        length2: 8,
        lineStyle: { color: rule }
      },
      data: [
        { value: 5, name: 'P0 高优先级', itemStyle: { color: danger } },
        { value: 9, name: 'P1 中优先级', itemStyle: { color: warn } },
        { value: 10, name: 'P2 低优先级', itemStyle: { color: accent2 } }
      ]
    }]
  });
  window.addEventListener('resize', function() { chart2.resize(); });

  // === Chart 3: Priority Matrix (Scatter) ===
  var chart3 = echarts.init(document.getElementById('chart-matrix'), null, { renderer: 'svg' });
  chart3.setOption({
    animation: false,
    tooltip: {
      appendToBody: true,
      formatter: function(p) {
        return '<b>' + p.data[3] + '</b><br/>影响: ' + p.data[1] + '/10<br/>成本: ' + p.data[0] + '/10<br/>优先级: ' + p.data[4];
      },
      textStyle: { fontSize: 12 }
    },
    legend: {
      data: ['P0 高优先级', 'P1 中优先级', 'P2 低优先级'],
      bottom: 0,
      textStyle: { color: muted, fontSize: 11 },
      itemWidth: 12,
      itemHeight: 12,
      itemGap: 16
    },
    grid: { left: '3%', right: '5%', bottom: '12%', top: '8%', containLabel: true },
    xAxis: {
      type: 'value',
      name: '实现成本 (低 → 高)',
      nameLocation: 'middle',
      nameGap: 28,
      nameTextStyle: { color: muted, fontSize: 11 },
      min: 0,
      max: 11,
      axisLine: { lineStyle: { color: rule } },
      axisLabel: { color: muted, fontSize: 11 },
      splitLine: { lineStyle: { color: rule, type: 'dashed' } }
    },
    yAxis: {
      type: 'value',
      name: '用户影响 (低 → 高)',
      nameLocation: 'middle',
      nameGap: 35,
      nameTextStyle: { color: muted, fontSize: 11 },
      min: 0,
      max: 11,
      axisLine: { show: false },
      axisLabel: { color: muted, fontSize: 11 },
      splitLine: { lineStyle: { color: rule, type: 'dashed' } }
    },
    series: [
      {
        name: 'P0 高优先级',
        type: 'scatter',
        symbolSize: 18,
        data: [
          [3, 10, 5, 'API 无认证', 'P0'],
          [2, 9, 5, '错误格式不统一', 'P0'],
          [1, 8, 5, '缺少 Error Boundary', 'P0'],
          [1, 7, 5, 'Toggle ARIA 缺失', 'P0'],
          [2, 7, 5, '下拉菜单无键盘', 'P0']
        ],
        itemStyle: { color: danger, opacity: 0.85, borderColor: '#fff', borderWidth: 2 }
      },
      {
        name: 'P1 中优先级',
        type: 'scatter',
        symbolSize: 14,
        data: [
          [3, 7, 9, '请求模式不统一', 'P1'],
          [3, 6, 9, 'Suspense 无骨架屏', 'P1'],
          [4, 6, 9, 'Gallery 代码重复', 'P1'],
          [1, 6, 9, 'CORS 缺失', 'P1'],
          [2, 5, 9, 'ConfigPayload 绕过', 'P1'],
          [3, 5, 9, '错误恢复粗暴', 'P1'],
          [4, 5, 9, '不支持移动端', 'P1'],
          [3, 4, 9, 'Context 错误静默', 'P1'],
          [2, 4, 9, '路由文档缺失', 'P1'],
          [6, 4, 9, 'CLI 手动解析', 'P1'],
          [2, 3, 9, 'CLI 无进度条', 'P1']
        ],
        itemStyle: { color: warn, opacity: 0.85, borderColor: '#fff', borderWidth: 2 }
      },
      {
        name: 'P2 低优先级',
        type: 'scatter',
        symbolSize: 12,
        data: [
          [1, 5, 10, '图标无 aria-label', 'P2'],
          [1, 4, 10, 'title/lang 未设置', 'P2'],
          [2, 4, 10, 'ConfigHub 草稿覆盖', 'P2'],
          [2, 3, 10, '轮询重建风险', 'P2'],
          [2, 3, 10, 'window.confirm 弹窗', 'P2'],
          [1, 3, 10, 'Google Fonts 依赖', 'P2'],
          [1, 2, 10, '硬编码分组', 'P2'],
          [3, 4, 10, 'Toast 通知系统', 'P2'],
          [1, 2, 10, '成功格式不统一', 'P2'],
          [2, 3, 10, 'DELETE 用 query', 'P2'],
          [1, 2, 10, 'launch.py 硬编码', 'P2'],
          [2, 3, 10, 'config warnings→500', 'P2'],
          [2, 2, 10, 'CLI help 排版', 'P2'],
          [2, 2, 10, '引擎启动无确认', 'P2'],
          [3, 2, 10, '任务选择无搜索', 'P2'],
          [1, 2, 10, 'convert 无确认', 'P2'],
          [2, 2, 10, 'Doctor 无 dry-run', 'P2'],
          [1, 2, 10, 'Doctor 无颜色', 'P2']
        ],
        itemStyle: { color: accent2, opacity: 0.75, borderColor: '#fff', borderWidth: 1 }
      }
    ]
  });
  window.addEventListener('resize', function() { chart3.resize(); });
})();
