var route = Ember.Route.extend({
  setupController: function(controller) {
    model = this.store.createRecord('task', {});
    controller.set('model', model);
  }
});

module.exports = route;
