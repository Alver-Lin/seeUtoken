import { createApp } from 'vue';
import Antd from 'ant-design-vue';
import 'ant-design-vue/dist/reset.css';
import '../../styles/global.css';
import '../../styles/glassControls.css';
import '../../styles/dashboardToolbar.css';
import '../../styles/usageRecords.css';
import App from './App.vue';
import { appearanceRoot, mountWithAppearance } from '../../utils/mainAppearance';
import CodexDashboard from './CodexDashboard.vue';

const provider = new URLSearchParams(window.location.search).get('provider');
document.title = provider === 'codex' ? 'seeUtoken · Codex 用量' : 'seeUtoken · Cursor 用量';
const page = provider === 'codex' ? CodexDashboard : App;
mountWithAppearance(createApp(appearanceRoot(page)).use(Antd));
