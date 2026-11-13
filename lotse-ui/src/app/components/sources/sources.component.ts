import { Component } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { TabsModule } from 'primeng/tabs';
import { GitSourcesComponent } from '../git-sources/git-sources.component';
import { ImageSourcesComponent } from '../image-sources/image-sources.component';

/** Where package versions come from: Git repositories (tags) and container images (registry tags). */
@Component({
    selector: 'app-sources',
    standalone: true,
    imports: [TabsModule, GitSourcesComponent, ImageSourcesComponent],
    template: `
        <div class="flex flex-col w-full min-h-full">
            <div class="mb-4">
                <h1 class="text-2xl font-semibold text-gray-900 dark:text-gray-50 mb-1">Sources</h1>
                <p class="text-sm text-gray-500 dark:text-gray-400">
                    Lotse watches these and deploys every new version tag. No zip, no config upload.
                </p>
            </div>
            <p-tabs [value]="tab">
                <p-tablist>
                    <p-tab value="git"><i class="pi pi-sync mr-2"></i>Git repositories</p-tab>
                    <p-tab value="images"><i class="pi pi-box mr-2"></i>Container images</p-tab>
                </p-tablist>
                <p-tabpanels>
                    <p-tabpanel value="git"><app-git-sources [embedded]="true" /></p-tabpanel>
                    <p-tabpanel value="images"><app-image-sources [embedded]="true" /></p-tabpanel>
                </p-tabpanels>
            </p-tabs>
        </div>
    `,
})
export class SourcesComponent {
    tab: string;

    constructor(route: ActivatedRoute) {
        this.tab = route.snapshot.queryParamMap.get('tab') === 'images' ? 'images' : 'git';
    }
}
