import { createApp } from "vue";
import {
  ElButton,
  ElDialog,
  ElDropdown,
  ElDropdownItem,
  ElDropdownMenu,
  ElForm,
  ElFormItem,
  ElIcon,
  ElInput,
  ElScrollbar,
} from "element-plus";
import "element-plus/theme-chalk/base.css";
import "element-plus/theme-chalk/el-button.css";
import "element-plus/theme-chalk/el-dialog.css";
import "element-plus/theme-chalk/el-dropdown.css";
import "element-plus/theme-chalk/el-dropdown-item.css";
import "element-plus/theme-chalk/el-form.css";
import "element-plus/theme-chalk/el-form-item.css";
import "element-plus/theme-chalk/el-icon.css";
import "element-plus/theme-chalk/el-input.css";
import "element-plus/theme-chalk/el-message.css";
import "element-plus/theme-chalk/el-overlay.css";
import "element-plus/theme-chalk/el-scrollbar.css";
import "./index.css";
import App from "./App.vue";

createApp(App)
  .use(ElButton)
  .use(ElDialog)
  .use(ElDropdown)
  .use(ElDropdownItem)
  .use(ElDropdownMenu)
  .use(ElForm)
  .use(ElFormItem)
  .use(ElIcon)
  .use(ElInput)
  .use(ElScrollbar)
  .mount("#app");
