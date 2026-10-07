import { createApp } from 'vue';
import App from './App.vue';
import router from './router';
import '@crr-brand/styles/tokens.css';
import '@crr-brand/styles/base.css';
import '@crr-brand/styles/components.css';
import './styles.css';

createApp(App).use(router).mount('#app');
