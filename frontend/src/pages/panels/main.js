import { createApp } from 'vue';
import Antd from 'ant-design-vue';
import 'ant-design-vue/dist/reset.css';
import '../../styles/global.css';
import '../../styles/glassControls.css';
import App from './App.vue';
import { appearanceRoot, mountWithAppearance } from '../../utils/mainAppearance';

const page = App;
mountWithAppearance(createApp(appearanceRoot(page)).use(Antd));
