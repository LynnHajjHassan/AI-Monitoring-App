const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const script = fs.readFileSync(path.join(__dirname, '../src/http/preview_page.h'), 'utf8').split('<script>')[1].split('</script>')[0];
function page() {
  const nodes = {};
  const context = vm.createContext({
    document:{getElementById:id => nodes[id] ??= {removeAttribute(){}}},
    performance:{now:() => 40000},
    setInterval(){}, clearTimeout(){}, window:{addEventListener(){}},
  });
  vm.runInContext(script, context);
  return {run:code => vm.runInContext(code, context), nodes};
}
test('time expiry works without new captures and disables empty export', () => {
  const {run, nodes} = page();
  run('frames = [{monotonicMs:10000,blob:{size:10}}, {monotonicMs:11000,blob:{size:10}}]; prune(40000)');
  assert.equal(run('frames.length'), 1);
  run('prune(41000)');
  assert.equal(run('frames.length'), 0);
  assert.equal(nodes.export.disabled, true);
});
test('count and byte limits discard oldest samples', () => {
  const {run} = page();
  run('frames = Array.from({length:40}, (_,i) => ({monotonicMs:39000+i,blob:{size:10}})); prune(40000)');
  assert.equal(run('frames.length'), 30);
  assert.equal(run('frames[0].monotonicMs'), 39010);
  run('frames = Array.from({length:5}, (_,i) => ({monotonicMs:39000+i,blob:{size:2*1024*1024}})); prune(40000)');
  assert.equal(run('frames.length'), 3);
  assert.equal(run('frames[0].monotonicMs'), 39002);
});
